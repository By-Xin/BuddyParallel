from __future__ import annotations

import json
from datetime import datetime
import threading
from dataclasses import dataclass
from time import sleep, time
from uuid import uuid4

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
from buddy_parallel.services.embedded_mqtt_helper import build_helper_html
from buddy_parallel.services.mqtt_notice_bridge import (
    deliver_mqtt_notice_payload,
    effective_mqtt_client_id,
    parse_mqtt_endpoint,
)
from buddy_parallel.services.notice_bridge_common import deliver_text_notice
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
        self.aggregator = StateAggregator(config=config)
        initial_state = self.state_store.load()
        if config.weather_enabled and isinstance(initial_state.last_weather_payload, dict):
            self.aggregator.set_weather(initial_state.last_weather_payload)
        self.permission_bridge = PermissionBridge(self.aggregator)
        self._stop = threading.Event()
        self._threads = RuntimeThreads()
        self._serial_session_lock = threading.Lock()
        self._device_io_lock = threading.RLock()
        self._serial_bootstrapped = False
        self._last_device_status: dict | None = None
        self._notice_reinforce_lock = threading.Lock()
        self._notice_reinforce_token = 0
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
        self.api_server = ApiServer(
            "127.0.0.1",
            config.api_server_port,
            self.on_api_event,
            self.on_vscode_permission_request,
            self.on_bridge_feishu_notice,
            self.on_bridge_feishu_status,
            self.on_bridge_mqtt_notice,
            self.on_bridge_mqtt_status,
            self.on_bridge_mqtt_config,
            self.on_bridge_mqtt_helper_page,
            self.on_hardware_refresh,
            self.on_hardware_command,
        )

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
        self.logger.info(
            "permission prompt published request_id=%s transport=%s",
            entry.request_id,
            self.device_manager.active_name or "none",
        )
        self.logger.info("permission pending request_id=%s tool=%s", entry.request_id, payload.get("tool_name", "Unknown"))
        decision = self.permission_bridge.wait_for_decision(entry.request_id)
        self._publish_heartbeat()
        self.logger.info("permission resolved request_id=%s decision=%s", entry.request_id, decision)
        self.permission_bridge.send_hook_response(handler, decision)

    def on_vscode_permission_request(self, payload: dict) -> dict:
        session_id = str(payload.get("session_id") or "vscode")
        request_payload = {
            "request_id": str(payload.get("request_id") or f"vscode-{uuid4().hex[:10]}"),
            "session_id": session_id,
            "tool_name": str(payload.get("tool_name") or "VS Code action"),
            "tool_input": payload.get("tool_input") or {},
        }
        entry = self.permission_bridge.register(request_payload)
        self._publish_heartbeat()
        self.logger.info(
            "vscode permission prompt published request_id=%s transport=%s",
            entry.request_id,
            self.device_manager.active_name or "none",
        )
        self.logger.info("vscode permission pending request_id=%s tool=%s", entry.request_id, request_payload["tool_name"])
        decision = self.permission_bridge.wait_for_decision(entry.request_id, timeout=float(payload.get("timeout_seconds") or 590.0))
        self._publish_heartbeat()
        self.logger.info("vscode permission resolved request_id=%s decision=%s", entry.request_id, decision)
        return {
            "ok": True,
            "request_id": entry.request_id,
            "decision": decision,
            "allowed": decision == "allow",
        }

    def on_bridge_mqtt_helper_page(self) -> str:
        return build_helper_html(f"http://127.0.0.1:{self.config.api_server_port}")

    def on_bridge_feishu_status(self, payload: dict) -> dict:
        connected = bool(payload.get("connected", False))
        last_error = str(payload.get("last_error") or "").strip()
        summary = str(payload.get("last_message_summary") or "").strip()
        self.logger.info(
            "feishu bridge status connected=%s summary=%s error=%s",
            connected,
            summary,
            last_error,
        )
        updates = {"feishu_connected": connected}
        if not last_error:
            updates["last_feishu_error"] = ""
        if last_error:
            updates["last_feishu_error"] = last_error
        if summary:
            updates["last_feishu_message_summary"] = summary[:40]
        self.state_store.update(**updates)
        return {"ok": True}

    def on_bridge_feishu_notice(self, payload: dict) -> dict:
        chat_id = str(payload.get("chat_id") or "").strip()
        if chat_id and chat_id != self.config.feishu_allowed_chat_id:
            return {"ok": True, "accepted": False}

        text = ""
        raw_content = payload.get("content")
        if isinstance(raw_content, str):
            try:
                content_payload = json.loads(raw_content or "{}")
            except Exception:
                content_payload = {}
            if isinstance(content_payload, dict):
                text = str(content_payload.get("text") or "").strip()
        if not text:
            return {"ok": True, "accepted": False}

        create_time = payload.get("create_time")
        stamp = ""
        try:
            raw = int(create_time or 0)
            if raw > 0:
                moment = datetime.fromtimestamp(raw / 1000 if raw > 10**11 else raw)
                stamp = moment.strftime("%d %b %H:%M")
        except (TypeError, ValueError, OSError):
            stamp = ""

        message_id = str(payload.get("message_id") or int(time() * 1000))
        deliver_text_notice(
            self.post_transient_message,
            text,
            base_notice_id=f"feishu-{message_id}",
            notice_from="B.Y.",
            notice_stamp=stamp,
        )
        self.state_store.update(
            feishu_connected=True,
            last_feishu_error="",
            last_feishu_message_summary=text[:40],
            last_feishu_delivery_at=time(),
        )
        return {"ok": True, "accepted": True}

    def on_bridge_mqtt_config(self) -> dict:
        try:
            endpoint = parse_mqtt_endpoint(self.config.notice_mqtt_url)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        if endpoint.transport != "websockets":
            return {"ok": False, "error": "embedded helper only supports ws or wss notice URLs"}
        if not self.config.notice_mqtt_topic:
            return {"ok": False, "error": "missing MQTT notice topic"}
        if not self.config.notice_mqtt_username or not self.config.notice_mqtt_password:
            return {"ok": False, "error": "missing MQTT notice credentials"}

        return {
            "ok": True,
            "url": self.config.notice_mqtt_url,
            "topic": self.config.notice_mqtt_topic,
            "username": self.config.notice_mqtt_username,
            "password": self.config.notice_mqtt_password,
            "clientId": effective_mqtt_client_id(self.config),
            "keepaliveSeconds": max(10, self.config.notice_mqtt_keepalive_seconds),
        }

    def on_bridge_mqtt_status(self, payload: dict) -> dict:
        connected = bool(payload.get("connected", False))
        last_error = str(payload.get("last_error") or "").strip()
        summary = str(payload.get("last_message_summary") or "").strip()
        self.logger.info(
            "embedded mqtt status connected=%s summary=%s error=%s",
            connected,
            summary,
            last_error,
        )
        updates = {
            "mqtt_connected": connected,
        }
        if not last_error:
            updates["last_mqtt_error"] = ""
        if last_error:
            updates["last_mqtt_error"] = last_error
        if summary:
            updates["last_mqtt_message_summary"] = summary[:40]
        self.state_store.update(**updates)
        return {"ok": True}

    def on_bridge_mqtt_notice(self, payload: dict) -> dict:
        accepted = deliver_mqtt_notice_payload(
            payload=payload.get("payload"),
            topic=str(payload.get("topic") or self.config.notice_mqtt_topic),
            retain=bool(payload.get("retain", False)),
            logger=self.logger,
            state_store=self.state_store,
            message_sink=self.post_transient_message,
        )
        return {"ok": True, "accepted": accepted}

    def on_hardware_refresh(self) -> dict:
        try:
            status = self.refresh_device_status()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if status is None:
            return {"ok": False, "error": "device transport is unavailable"}
        return {"ok": True, "status": status}

    def on_hardware_command(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "payload must be a JSON object"}
        command_payload = payload.get("command")
        if not isinstance(command_payload, dict):
            return {"ok": False, "error": "command must be a JSON object"}
        refresh = bool(payload.get("refresh", True))
        try:
            status = self.apply_device_command(command_payload, refresh=refresh)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if status is None:
            return {"ok": False, "error": "device transport is unavailable"}
        return {"ok": True, "status": status}

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
        self._ble.close()
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
            "device_port": self._serial.port,
            "serial": serial_summary(self.config.serial_port),
            "ble": ble_summary(self.config.ble_device_name),
            "device_status": self._last_device_status,
        }

    def latest_device_status(self) -> dict | None:
        return self._last_device_status

    def refresh_device_status(self) -> dict | None:
        with self._device_io_lock:
            transport = self._control_transport()
            if transport is None:
                return None
            status = transport.request_status()
            if status is not None:
                self._last_device_status = status
                self._write_runtime_snapshot("running")
            return status

    def apply_device_command(self, payload: dict, refresh: bool = True) -> dict | None:
        with self._device_io_lock:
            transport = self._control_transport()
            if transport is None:
                raise RuntimeError("device transport is unavailable")
            transport.send_json(payload)
            status = transport.request_status() if refresh else self._last_device_status
            if status is not None:
                self._last_device_status = status
            self._write_runtime_snapshot("running")
            return status

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
                ready = False
                line = ""
                with self._device_io_lock:
                    ready = self._ensure_serial_session()
                    if ready:
                        line = self._serial.read_line(timeout=0.25)
                    else:
                        self.device_manager.active_name = ""
                if not ready:
                    self._stop.wait(1.0)
                    continue
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
                with self._device_io_lock:
                    if self._ensure_serial_session():
                        self._serial.send_json(heartbeat)
                        self.device_manager.active_name = self._serial.name
                        return
            except Exception as exc:
                self.logger.warning("serial heartbeat failed: %s", exc)
                self._reset_serial_session()

        self._mock.send_json(heartbeat)
        self.device_manager.active_name = self._mock.name

    def _control_transport(self):
        if self.config.transport_mode in {"auto", "serial"} and self._ensure_serial_session():
            self.device_manager.active_name = self._serial.name
            return self._serial
        if self.config.transport_mode in {"auto", "ble"} and self._ble.open():
            self._ble.send_handshake(owner_name=self.config.owner_name, device_name=self.config.device_name)
            self.device_manager.active_name = self._ble.name
            return self._ble
        return None

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
            # Kick off a status refresh, but do not block the caller here.
            # Permission prompts and other heartbeats should reach the board
            # immediately after bootstrap instead of waiting through a full
            # synchronous status round-trip.
            self._serial.send_json({"cmd": "status"})
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
            if dismissed:
                self._schedule_notice_reinforcement()
            self.logger.info("device notice id=%s action=%s", notice_id, action or "ack")
            self.logger.info("device notice id=%s dismissed=%s", notice_id, dismissed)
            return

        if payload.get("ack") == "status":
            self._last_device_status = payload
            self._write_runtime_snapshot("running")
            return

        if isinstance(payload.get("ack"), str):
            self.logger.info("device ack=%s ok=%s", payload.get("ack"), payload.get("ok"))

    def _publish_heartbeat(self) -> None:
        heartbeat = self.aggregator.build_heartbeat()
        self._send_heartbeat(heartbeat)
        self._write_runtime_snapshot("running")

    def _schedule_notice_reinforcement(self) -> None:
        heartbeat = self.aggregator.build_heartbeat()
        if not heartbeat.get("notice"):
            return
        with self._notice_reinforce_lock:
            self._notice_reinforce_token += 1
            token = self._notice_reinforce_token

        def worker() -> None:
            for delay_seconds in (0.25, 1.0):
                if self._stop.wait(delay_seconds):
                    return
                with self._notice_reinforce_lock:
                    if token != self._notice_reinforce_token:
                        return
                try:
                    self._publish_heartbeat()
                except Exception:
                    self.logger.exception("notice reinforcement heartbeat failed")

        threading.Thread(target=worker, name="notice-reinforce", daemon=True).start()

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
                "device_port": self._serial.port,
                "heartbeat": heartbeat,
                "device_status": self._last_device_status,
            }
        )
