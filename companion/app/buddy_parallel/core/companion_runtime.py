from __future__ import annotations

import threading
from dataclasses import dataclass
from time import sleep

from buddy_parallel.core.aggregator import StateAggregator
from buddy_parallel.core.device_manager import DeviceManager
from buddy_parallel.core.event_mapper import normalize_event
from buddy_parallel.core.permission_bridge import PermissionBridge
from buddy_parallel.ingest.api_server import ApiServer
from buddy_parallel.ingest.hook_server import HookServer
from buddy_parallel.runtime.config import AppConfig
from buddy_parallel.runtime.logging_utils import configure_logging
from buddy_parallel.runtime.runtime_config import write_runtime_config
from buddy_parallel.runtime.state import RuntimeState, StateStore
from buddy_parallel.transports.ble_transport import BleTransport
from buddy_parallel.transports.mock_transport import MockTransport
from buddy_parallel.transports.serial_transport import SerialTransport, send_bootstrap_and_heartbeat, serial_summary


@dataclass
class RuntimeThreads:
    hook_thread: threading.Thread | None = None
    api_thread: threading.Thread | None = None
    heartbeat_thread: threading.Thread | None = None


class CompanionRuntime:
    def __init__(self, config: AppConfig, state_store: StateStore | None = None) -> None:
        self.config = config
        self.logger = configure_logging()
        self.state_store = state_store or StateStore()
        self.aggregator = StateAggregator()
        self.permission_bridge = PermissionBridge(self.aggregator)
        self._stop = threading.Event()
        self._threads = RuntimeThreads()
        self._mock = MockTransport()
        self._serial = SerialTransport(port=config.serial_port, baud=config.serial_baud)
        self._ble = BleTransport(device_name=config.ble_device_name)
        transports = [self._mock]
        if config.transport_mode in {"auto", "serial"}:
            transports.insert(0, self._serial)
        if config.transport_mode in {"auto", "ble"}:
            transports.append(self._ble)
        self.device_manager = DeviceManager(transports=transports)
        self.hook_server = HookServer("127.0.0.1", config.hook_server_port, self.on_state_event, self.on_permission_request)
        self.api_server = ApiServer("127.0.0.1", config.api_server_port, self.on_api_event)

    def on_state_event(self, payload: dict) -> None:
        normalized = normalize_event(payload)
        self.aggregator.apply_event(normalized)
        if normalized.get("event") in {"SessionEnd", "Stop", "PostToolUse", "PostToolUseFailure"}:
            self.permission_bridge.clear_for_session(normalized["session_id"])
        self.logger.info("state event session=%s event=%s state=%s", normalized["session_id"], normalized["event"], normalized["state"])

    def on_api_event(self, payload: dict) -> None:
        payload.setdefault("source", "api")
        self.aggregator.apply_event(normalize_event(payload))
        self.logger.info("api event applied session=%s", payload.get("session_id", "default"))

    def on_permission_request(self, handler, payload: dict) -> None:
        request_id = self.permission_bridge.register(handler, payload)
        self.logger.info("permission pending request_id=%s tool=%s", request_id, payload.get("tool_name", "Unknown"))

    def start(self) -> None:
        self.hook_server.start()
        self.api_server.start()
        self._threads.hook_thread = threading.Thread(target=self.hook_server.serve_forever, name="hook-server", daemon=True)
        self._threads.api_thread = threading.Thread(target=self.api_server.serve_forever, name="api-server", daemon=True)
        self._threads.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="heartbeat-loop", daemon=True)
        self._threads.hook_thread.start()
        self._threads.api_thread.start()
        self._threads.heartbeat_thread.start()
        self._write_runtime_snapshot("running")

    def stop(self) -> None:
        self._stop.set()
        self.hook_server.shutdown()
        self.api_server.shutdown()
        self._write_runtime_snapshot("stopped")

    def run_forever(self) -> None:
        self.start()
        try:
            while not self._stop.is_set():
                sleep(0.25)
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received; stopping runtime")
            self.stop()

    def snapshot(self) -> dict:
        heartbeat = self.aggregator.build_heartbeat()
        transport_name = self.device_manager.active_name or self.device_manager.active_transport().name if self.device_manager.active_transport() else ""
        return {
            "heartbeat": heartbeat,
            "transport": transport_name,
            "serial": serial_summary(self.config.serial_port),
        }

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            heartbeat = self.aggregator.build_heartbeat()
            self._send_heartbeat(heartbeat)
            self._write_runtime_snapshot("running")
            self._stop.wait(10.0)

    def _send_heartbeat(self, heartbeat: dict) -> None:
        if self.config.transport_mode == "mock":
            self._mock.send_json(heartbeat)
            self.device_manager.active_name = self._mock.name
            return

        if self.config.transport_mode in {"auto", "serial"} and self._serial.available():
            try:
                send_bootstrap_and_heartbeat(
                    port=self._serial.port,
                    baud=self.config.serial_baud,
                    owner_name=self.config.owner_name,
                    device_name=self.config.device_name,
                    heartbeat=heartbeat,
                )
                self.device_manager.active_name = self._serial.name
                return
            except Exception as exc:
                self.logger.warning("serial heartbeat failed: %s", exc)

        self._mock.send_json(heartbeat)
        self.device_manager.active_name = self._mock.name

    def _write_runtime_snapshot(self, status: str) -> None:
        heartbeat = self.aggregator.build_heartbeat()
        active = self.device_manager.active_name or ""
        state = RuntimeState(last_transport=active, last_device_id=self._serial.port, last_status=status, last_error="")
        self.state_store.save(state)
        write_runtime_config(
            {
                "hook_server_port": self.config.hook_server_port,
                "api_server_port": self.config.api_server_port,
                "transport": active,
                "heartbeat": heartbeat,
            }
        )
