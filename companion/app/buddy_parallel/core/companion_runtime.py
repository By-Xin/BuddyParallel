from __future__ import annotations

import json
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
from buddy_parallel.transports.ble_transport import BleTransport, ble_summary
from buddy_parallel.transports.mock_transport import MockTransport
from buddy_parallel.transports.serial_transport import SerialTransport, serial_summary


@dataclass
class RuntimeThreads:
    hook_thread: threading.Thread | None = None
    api_thread: threading.Thread | None = None
    serial_thread: threading.Thread | None = None
    heartbeat_thread: threading.Thread | None = None


class CompanionRuntime:
    def __init__(self, config: AppConfig, state_store: StateStore | None = None) -> None:
        self.config = config
        self.logger = configure_logging()
        self.state_store = state_store or StateStore()
        self.aggregator = StateAggregator()
        initial_state = self.state_store.load()
        if config.weather_enabled and isinstance(initial_state.last_weather_payload, dict):
            self.aggregator.set_weather(initial_state.last_weather_payload)
        self.permission_bridge = PermissionBridge(self.aggregator)
        self._stop = threading.Event()
        self._threads = RuntimeThreads()
        self._serial_session_lock = threading.Lock()
        self._serial_bootstrapped = False
        self._last_device_status: dict | None = None
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
        if normalized.get("event") == "SessionEnd":
            self.permission_bridge.clear_for_session(normalized["session_id"])
        self._publish_heartbeat()
        self.logger.info("state event session=%s event=%s state=%s", normalized["session_id"], normalized["event"], normalized["state"])

    def on_api_event(self, payload: dict) -> None:
        payload.setdefault("source", "api")
        self.aggregator.apply_event(normalize_event(payload))
        self._publish_heartbeat()
        self.logger.info("api event applied session=%s", payload.get("session_id", "default"))

    def on_permission_request(self, handler, payload: dict) -> None:
        entry = self.permission_bridge.register(payload)
        self._publish_heartbeat()
        self.logger.info("permission pending request_id=%s tool=%s", entry.request_id, payload.get("tool_name", "Unknown"))
        decision = self.permission_bridge.wait_for_decision(entry.request_id)
        self._publish_heartbeat()
        self.logger.info("permission resolved request_id=%s decision=%s", entry.request_id, decision)
        self.permission_bridge.send_hook_response(handler, decision)

    def start(self) -> None:
        self.hook_server.start()
        self.api_server.start()
        self._threads.hook_thread = threading.Thread(target=self.hook_server.serve_forever, name="hook-server", daemon=True)
        self._threads.api_thread = threading.Thread(target=self.api_server.serve_forever, name="api-server", daemon=True)
        self._threads.serial_thread = threading.Thread(target=self._serial_loop, name="serial-loop", daemon=True)
        self._threads.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="heartbeat-loop", daemon=True)
        self._threads.hook_thread.start()
        self._threads.api_thread.start()
        self._threads.serial_thread.start()
        self._threads.heartbeat_thread.start()
        self._write_runtime_snapshot("running")

    def stop(self) -> None:
        self._stop.set()
        self.permission_bridge.cancel_all()
        self.hook_server.shutdown()
        self.api_server.shutdown()
        self._reset_serial_session()
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
        transport_name = self.device_manager.active_name or (self._serial.name if self._serial.is_open else "")
        return {
            "heartbeat": heartbeat,
            "transport": transport_name,
            "serial": serial_summary(self.config.serial_port),
            "ble": ble_summary(self.config.ble_device_name),
            "device_status": self._last_device_status,
        }

    def post_transient_message(
        self,
        message: str,
        entries: list[str] | None = None,
        ttl_seconds: float = 45.0,
        notice_id: str = "",
        notice_from: str = "",
        notice_body: str = "",
        notice_stamp: str = "",
    ) -> None:
        self.aggregator.post_transient(
            message=message,
            entries=entries,
            ttl_seconds=ttl_seconds,
            notice_id=notice_id,
            notice_from=notice_from,
            notice_body=notice_body,
            notice_stamp=notice_stamp,
        )
        self._publish_heartbeat()

    def set_weather_snapshot(self, payload: dict | None) -> None:
        self.aggregator.set_weather(payload)
        self._publish_heartbeat()

    def _serial_loop(self) -> None:
        while not self._stop.is_set():
            if self.config.transport_mode not in {"auto", "serial"}:
                self._stop.wait(1.0)
                continue
            try:
                if not self._ensure_serial_session():
                    self.device_manager.active_name = ""
                    self._stop.wait(1.0)
                    continue
                line = self._serial.read_line(timeout=0.25)
                if line:
                    self._handle_device_line(line)
            except Exception as exc:
                self.logger.warning("serial loop failed: %s", exc)
                self._reset_serial_session()
                self._stop.wait(1.0)

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            self._publish_heartbeat()
            self._stop.wait(10.0)

    def _send_heartbeat(self, heartbeat: dict) -> None:
        if self.config.transport_mode == "mock":
            self._mock.send_json(heartbeat)
            self.device_manager.active_name = self._mock.name
            return

        if self.config.transport_mode in {"auto", "serial"}:
            try:
                if self._ensure_serial_session():
                    self._serial.send_json(heartbeat)
                    self.device_manager.active_name = self._serial.name
                    return
            except Exception as exc:
                self.logger.warning("serial heartbeat failed: %s", exc)
                self._reset_serial_session()

        self._mock.send_json(heartbeat)
        self.device_manager.active_name = self._mock.name

    def _ensure_serial_session(self) -> bool:
        if self.config.transport_mode not in {"auto", "serial"}:
            return False
        if not self._serial.available():
            return False
        with self._serial_session_lock:
            if self._serial_bootstrapped and self._serial.is_open:
                return True
            if not self._serial.open():
                return False
            sleep(1.5)
            boot_lines = self._serial.drain_lines()
            for line in boot_lines:
                self.logger.info("device boot line %s", line)
            self._serial.send_handshake(owner_name=self.config.owner_name, device_name=self.config.device_name)
            self.device_manager.active_name = self._serial.name
            self._serial_bootstrapped = True
            self.logger.info("serial transport connected on %s", self._serial.port)
            status = self._serial.request_status()
            if status:
                self._last_device_status = status
                self.logger.info("device status received on %s", self._serial.port)
            return True

    def _reset_serial_session(self) -> None:
        with self._serial_session_lock:
            self._serial_bootstrapped = False
            self._serial.close()
            if self.device_manager.active_name == self._serial.name:
                self.device_manager.active_name = ""

    def _handle_device_line(self, line: str) -> None:
        self.logger.info("device line %s", line)
        if not line.startswith("{"):
            return
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return

        if payload.get("cmd") == "permission":
            request_id = str(payload.get("id") or "")
            decision = str(payload.get("decision") or "")
            if request_id and decision:
                resolved = self.permission_bridge.resolve_from_device(request_id, decision)
                self._publish_heartbeat()
                self.logger.info("device permission request_id=%s decision=%s resolved=%s", request_id, decision, resolved)
            return

        if payload.get("cmd") == "notice_ack":
            notice_id = str(payload.get("id") or "")
            action = str(payload.get("action") or "")
            dismissed = self.aggregator.dismiss_notice(notice_id)
            self._publish_heartbeat()
            self.logger.info("device notice id=%s action=%s", notice_id, action or "ack")
            self.logger.info("device notice id=%s dismissed=%s", notice_id, dismissed)
            return

        if payload.get("ack") == "status":
            self._last_device_status = payload
            return

        if isinstance(payload.get("ack"), str):
            self.logger.info("device ack=%s ok=%s", payload.get("ack"), payload.get("ok"))

    def _publish_heartbeat(self) -> None:
        heartbeat = self.aggregator.build_heartbeat()
        self._send_heartbeat(heartbeat)
        self._write_runtime_snapshot("running")

    def _write_runtime_snapshot(self, status: str) -> None:
        heartbeat = self.aggregator.build_heartbeat()
        active = self.device_manager.active_name or ""
        state = self.state_store.load()
        state.last_transport = active
        state.last_device_id = self._serial.port
        state.last_status = status
        state.last_error = ""
        self.state_store.save(state)
        write_runtime_config(
            {
                "hook_server_port": self.config.hook_server_port,
                "api_server_port": self.config.api_server_port,
                "transport": active,
                "heartbeat": heartbeat,
                "device_status": self._last_device_status,
            }
        )
