from __future__ import annotations

import json
import logging
import re
import socket
import ssl
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import time
from typing import Any
from urllib.parse import urlparse

from buddy_parallel.runtime.config import APP_DIR, AppConfig
from buddy_parallel.runtime.state import StateStore
from buddy_parallel.services.embedded_mqtt_helper import build_helper_html
from buddy_parallel.services.notice_bridge_common import (
    DEFAULT_NOTICE_FROM,
    NoticeSink,
    build_mqtt_notice_chunks,
    emit_notice_chunks,
)

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

try:
    import socks
except ImportError:
    socks = None

try:
    import win32con
    import win32gui
    import win32process
except ImportError:
    win32con = None
    win32gui = None
    win32process = None


EDGE_HELPER_FILENAME = "mqtt-helper.html"
EDGE_HELPER_PATH = "/bridge/mqtt-helper"
EMBEDDED_BRIDGE_SUMMARY = "Embedded MQTT bridge"


@dataclass
class MqttBridgeStatus:
    mqtt_ok: bool = False
    last_error: str = ""
    last_message_summary: str = "idle"


@dataclass(frozen=True)
class MqttEndpoint:
    host: str
    port: int
    transport: str
    use_tls: bool
    websocket_path: str


@dataclass(frozen=True)
class ProxyCandidate:
    label: str
    proxy_args: dict[str, Any] | None = None


def parse_mqtt_endpoint(url: str) -> MqttEndpoint:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = parsed.hostname or ""
    if not host:
        raise ValueError("notice_mqtt_url must include a hostname")
    if scheme not in {"ws", "wss", "mqtt", "mqtts"}:
        raise ValueError("notice_mqtt_url must use ws, wss, mqtt, or mqtts")

    if scheme in {"ws", "wss"}:
        port = parsed.port or (443 if scheme == "wss" else 80)
        path = parsed.path or "/"
        return MqttEndpoint(
            host=host,
            port=port,
            transport="websockets",
            use_tls=scheme == "wss",
            websocket_path=path,
        )

    port = parsed.port or (8883 if scheme == "mqtts" else 1883)
    return MqttEndpoint(
        host=host,
        port=port,
        transport="tcp",
        use_tls=scheme == "mqtts",
        websocket_path="/",
    )


def effective_mqtt_client_id(config: AppConfig) -> str:
    explicit = str(config.notice_mqtt_client_id or "").strip()
    if explicit:
        return explicit
    host = re.sub(r"[^a-z0-9]+", "-", socket.gethostname().lower()).strip("-") or "pc"
    user = re.sub(r"[^a-z0-9]+", "-", str(config.notice_mqtt_username or "").lower()).strip("-") or "mqtt"
    return f"bp-{host[:8]}-{user[:8]}"[:23]


def _parse_bool_line(line: str) -> bool | None:
    _, _, raw = line.partition(":")
    value = raw.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _parse_int_line(line: str) -> int | None:
    _, _, raw = line.partition(":")
    try:
        return int(raw.strip())
    except ValueError:
        return None


def detect_windows_proxy_candidates(endpoint: MqttEndpoint) -> list[ProxyCandidate]:
    candidates = [ProxyCandidate(label="direct")]
    if not sys.platform.startswith("win"):
        return candidates
    if endpoint.transport != "websockets" or socks is None:
        return candidates

    verge_path = APP_DIR.parent / "io.github.clash-verge-rev.clash-verge-rev" / "verge.yaml"
    config_path = APP_DIR.parent / "io.github.clash-verge-rev.clash-verge-rev" / "config.yaml"
    if not verge_path.exists() or not config_path.exists():
        return candidates

    try:
        verge_lines = verge_path.read_text(encoding="utf-8").splitlines()
        config_lines = config_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return candidates

    system_proxy_enabled = None
    proxy_auto_config = None
    mixed_port = None
    for line in verge_lines:
        stripped = line.strip()
        if stripped.startswith("enable_system_proxy:"):
            system_proxy_enabled = _parse_bool_line(stripped)
        elif stripped.startswith("proxy_auto_config:"):
            proxy_auto_config = _parse_bool_line(stripped)
        elif stripped.startswith("verge_mixed_port:"):
            mixed_port = _parse_int_line(stripped)

    if mixed_port is None:
        for line in config_lines:
            stripped = line.strip()
            if stripped.startswith("mixed-port:"):
                mixed_port = _parse_int_line(stripped)
                break

    if system_proxy_enabled is not True or mixed_port is None:
        return candidates

    # Clash Verge's PAC prefers HTTP proxy first, then SOCKS5, then DIRECT.
    # We mirror that order so Python can follow the same local proxy path
    # when raw direct sockets are blocked on this machine.
    candidates.extend(
        [
            ProxyCandidate(
                label=f"clash-http-127.0.0.1:{mixed_port}",
                proxy_args={
                    "proxy_type": socks.HTTP,
                    "proxy_addr": "127.0.0.1",
                    "proxy_port": mixed_port,
                    "proxy_rdns": True,
                },
            ),
            ProxyCandidate(
                label=f"clash-socks5-127.0.0.1:{mixed_port}",
                proxy_args={
                    "proxy_type": socks.SOCKS5,
                    "proxy_addr": "127.0.0.1",
                    "proxy_port": mixed_port,
                    "proxy_rdns": True,
                },
            ),
        ]
    )
    if proxy_auto_config is True:
        candidates.append(ProxyCandidate(label="direct-after-pac"))
    return candidates


def new_mqtt_client(client_id: str, transport: str):
    assert mqtt is not None
    try:
        return mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,
            client_id=client_id,
            transport=transport,
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )
    except AttributeError:
        return mqtt.Client(
            client_id=client_id,
            transport=transport,
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )


def deliver_mqtt_notice_payload(
    *,
    payload: Any,
    topic: str,
    retain: bool,
    logger: logging.Logger,
    state_store: StateStore,
    message_sink: NoticeSink,
) -> bool:
    if retain:
        logger.warning("Ignored retained MQTT notice on %s", topic)
        return False

    if not isinstance(payload, dict):
        logger.warning("Ignored MQTT notice payload with unsupported type on %s", topic)
        return False

    payload_type = str(payload.get("type") or "notice").strip().lower()
    if payload_type != "notice":
        logger.info("Ignored MQTT payload type=%s topic=%s", payload_type, topic)
        return False

    received_at = datetime.now()
    fallback_notice_id = f"mqtt-{int(time() * 1000)}"
    try:
        notices = build_mqtt_notice_chunks(
            payload,
            fallback_notice_id=fallback_notice_id,
            received_at=received_at,
        )
    except Exception as exc:
        logger.warning("Ignored malformed MQTT notice payload on %s: %s", topic, exc)
        return False

    emit_notice_chunks(message_sink, notices)
    summary = notices[0].summary if notices else "notice"
    state_store.update(
        mqtt_connected=True,
        last_mqtt_delivery_at=time(),
        last_mqtt_error="",
        last_mqtt_message_summary=summary[:40],
    )
    logger.info("Accepted MQTT notice on %s", topic)
    return True


class MqttNoticeBridge:
    def __init__(
        self,
        config_supplier,
        message_sink: NoticeSink,
        logger: logging.Logger,
        state_store: StateStore,
    ) -> None:
        self._config_supplier = config_supplier
        self._message_sink = message_sink
        self._logger = logger
        self._state_store = state_store
        self._runtime_state = self._state_store.load()
        self._status = MqttBridgeStatus(
            mqtt_ok=self._runtime_state.mqtt_connected,
            last_error=self._runtime_state.last_mqtt_error,
            last_message_summary=self._runtime_state.last_mqtt_message_summary,
        )
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._reload = threading.Event()
        self._lock = threading.Lock()
        self._client_lock = threading.Lock()
        self._helper_lock = threading.Lock()
        self._client = None
        self._helper_process: subprocess.Popen | None = None
        self._helper_profile_dir: Path | None = None
        self._expected_disconnect = False
        self._edge_path = self._find_edge_executable()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._reload.clear()
        self._thread = threading.Thread(target=self._run, name="bp-mqtt-notice", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._reload.set()
        self._disconnect_client()
        self._stop_helper_process()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def request_reload(self) -> None:
        self._runtime_state = self._state_store.load()
        self._reload.set()
        self._disconnect_client()
        self._stop_helper_process()

    def status(self) -> MqttBridgeStatus:
        state = self._state_store.load()
        with self._lock:
            return MqttBridgeStatus(
                mqtt_ok=bool(state.mqtt_connected or self._status.mqtt_ok),
                last_error=state.last_mqtt_error or self._status.last_error,
                last_message_summary=state.last_mqtt_message_summary or self._status.last_message_summary,
            )

    def _set_status(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self._status, key, value)

    def _sleep_or_reload(self, seconds: float) -> None:
        self._reload.wait(timeout=seconds)
        self._reload.clear()

    def _runtime_config_error(self, config: AppConfig) -> str:
        if not config.notice_mqtt_url or not config.notice_mqtt_topic:
            return "configure MQTT notice URL and topic"
        if not config.notice_mqtt_username or not config.notice_mqtt_password:
            return "configure MQTT notice credentials"
        return ""

    def _run(self) -> None:
        while not self._stop.is_set():
            config = self._config_supplier()
            config_error = self._runtime_config_error(config)
            if config_error:
                self._set_status(mqtt_ok=False, last_error=config_error)
                self._state_store.update(mqtt_connected=False, last_mqtt_error=config_error)
                self._sleep_or_reload(2.0)
                continue

            try:
                endpoint = parse_mqtt_endpoint(config.notice_mqtt_url)
                if self._should_use_embedded_bridge(endpoint):
                    self._run_embedded_bridge(config)
                else:
                    if mqtt is None:
                        raise RuntimeError("missing dependency: pip install paho-mqtt")
                    self._run_direct_bridge(config, endpoint)
            except Exception as exc:
                self._logger.exception("MQTT notice bridge failed")
                self._set_status(mqtt_ok=False, last_error=str(exc))
                self._state_store.update(mqtt_connected=False, last_mqtt_error=str(exc))
                self._sleep_or_reload(3.0)
            finally:
                self._reload.clear()
                self._disconnect_client()
                self._stop_helper_process()

    def _should_use_embedded_bridge(self, endpoint: MqttEndpoint) -> bool:
        # Keep the embedded helper available as an escape hatch, but do not
        # prefer it automatically. The primary goal is to make the direct
        # Python MQTT path work cleanly on Windows first.
        return False

    def _run_direct_bridge(self, config: AppConfig, endpoint: MqttEndpoint) -> None:
        errors: list[str] = []
        for candidate in detect_windows_proxy_candidates(endpoint):
            self._state_store.update(
                mqtt_connected=False,
                last_mqtt_error="",
                last_mqtt_message_summary=f"Connecting via {candidate.label}"[:40],
            )
            client = self._build_client(config, endpoint, proxy_args=candidate.proxy_args)
            with self._client_lock:
                self._client = client
                self._expected_disconnect = False
            try:
                client.connect(endpoint.host, endpoint.port, keepalive=max(10, config.notice_mqtt_keepalive_seconds))
            except Exception as exc:
                message = f"{candidate.label}: {exc}"
                errors.append(message)
                self._logger.warning("MQTT direct bridge candidate failed %s", message)
                self._disconnect_client()
                continue

            self._logger.info("MQTT direct bridge connected using %s", candidate.label)
            client.loop_start()
            while not self._stop.is_set() and not self._reload.is_set():
                self._stop.wait(0.25)
            return

        if errors:
            raise RuntimeError(" | ".join(errors))
        raise RuntimeError("no MQTT direct bridge candidates available")

    def _run_embedded_bridge(self, config: AppConfig) -> None:
        helper_target = self._embedded_helper_target(config.api_server_port)
        command = self._embedded_helper_command(helper_target)
        self._set_status(mqtt_ok=False, last_error="", last_message_summary=EMBEDDED_BRIDGE_SUMMARY)
        self._state_store.update(
            mqtt_connected=False,
            last_mqtt_error="",
            last_mqtt_message_summary=EMBEDDED_BRIDGE_SUMMARY,
        )
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        with self._helper_lock:
            self._helper_process = process
        self._logger.info("Embedded MQTT notice bridge started pid=%s", process.pid)
        while not self._stop.is_set() and not self._reload.is_set():
            if process.poll() is not None:
                raise RuntimeError(f"embedded MQTT helper exited rc={process.returncode}")
            self._stop.wait(0.5)

    def _build_client(self, config: AppConfig, endpoint: MqttEndpoint, proxy_args: dict[str, Any] | None = None):
        client = new_mqtt_client(client_id=effective_mqtt_client_id(config), transport=endpoint.transport)
        client.user_data_set(
            {
                "topic": config.notice_mqtt_topic,
                "default_from": DEFAULT_NOTICE_FROM,
            }
        )
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.username_pw_set(config.notice_mqtt_username, config.notice_mqtt_password or None)
        if proxy_args:
            client.proxy_set(**proxy_args)
        if endpoint.transport == "websockets":
            client.ws_set_options(
                path=endpoint.websocket_path,
                headers={"Origin": "null"},
            )
        if endpoint.use_tls:
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            client.tls_insecure_set(False)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        return client

    def _disconnect_client(self) -> None:
        client = None
        with self._client_lock:
            if self._client is None:
                return
            self._expected_disconnect = True
            client = self._client
            self._client = None
        try:
            client.disconnect()
        except Exception:
            pass
        try:
            client.loop_stop()
        except Exception:
            pass
        with self._client_lock:
            self._expected_disconnect = False

    def _stop_helper_process(self) -> None:
        process = None
        with self._helper_lock:
            process = self._helper_process
            self._helper_process = None
        if process is None:
            return
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=2.0)
            return
        except Exception:
            pass
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5.0,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass

    def _embedded_helper_target(self, api_server_port: int) -> str:
        helper_root = APP_DIR / "edge-mqtt-helper"
        helper_root.mkdir(parents=True, exist_ok=True)
        helper_file = helper_root / EDGE_HELPER_FILENAME
        api_base = f"http://127.0.0.1:{api_server_port}"
        helper_file.write_text(build_helper_html(api_base), encoding="utf-8")
        return helper_file.resolve().as_uri()

    def _embedded_helper_command(self, helper_target: str) -> list[str]:
        assert self._edge_path is not None
        profile_dir = APP_DIR / "edge-mqtt-helper" / f"session-{int(time() * 1000)}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._helper_profile_dir = profile_dir
        return [
            str(self._edge_path),
            f"--app={helper_target}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=320,240",
            "--window-position=-2400,-2400",
            f"--user-data-dir={profile_dir}",
        ]

    def _find_edge_executable(self) -> Path | None:
        candidates = [
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None


    def _on_connect(self, client, userdata: dict[str, Any], flags, rc) -> None:
        if rc != 0:
            message = f"MQTT connect failed rc={rc}"
            self._logger.warning(message)
            self._set_status(mqtt_ok=False, last_error=message)
            self._state_store.update(mqtt_connected=False, last_mqtt_error=message)
            return
        topic = str(userdata.get("topic") or "")
        client.subscribe(topic, qos=1)
        self._set_status(mqtt_ok=True, last_error="")
        self._state_store.update(
            mqtt_connected=True,
            last_mqtt_error="",
            last_mqtt_message_summary=f"Subscribed {topic}"[:40],
        )
        self._logger.info("MQTT notice bridge connected topic=%s", topic)

    def _on_disconnect(self, client, userdata, rc) -> None:
        with self._client_lock:
            expected = self._expected_disconnect
        if expected or self._stop.is_set():
            return
        message = f"MQTT notice bridge disconnected rc={rc}"
        self._logger.warning(message)
        self._set_status(mqtt_ok=False, last_error=message)
        self._state_store.update(mqtt_connected=False, last_mqtt_error=message)

    def _on_message(self, client, userdata: dict[str, Any], message) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except Exception:
            self._logger.warning("Ignored non-JSON MQTT notice payload on %s", message.topic)
            return

        accepted = deliver_mqtt_notice_payload(
            payload=payload,
            topic=message.topic,
            retain=bool(getattr(message, "retain", False)),
            logger=self._logger,
            state_store=self._state_store,
            message_sink=self._message_sink,
        )
        if accepted:
            runtime_state = self._state_store.load()
            self._set_status(
                mqtt_ok=True,
                last_error="",
                last_message_summary=runtime_state.last_mqtt_message_summary,
            )
