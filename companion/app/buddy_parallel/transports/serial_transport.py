from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime

from buddy_parallel.transports.base import TransportBase, sanitize_device_payload

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None


@dataclass
class SerialDeviceInfo:
    device: str
    description: str = ""
    manufacturer: str = ""


class SerialTransport(TransportBase):
    def __init__(self, port: str = "", baud: int = 115200) -> None:
        super().__init__(name="serial")
        self._configured_port = port
        self.baud = baud
        self._serial = None
        self._resolved_port = ""
        self._lock = threading.RLock()

    def available(self) -> bool:
        if serial is None:
            return False
        return bool(self.resolve_port())

    def resolve_port(self) -> str:
        if self._configured_port:
            self._resolved_port = self._configured_port
            return self._resolved_port
        ports = discover_serial_devices()
        if not ports:
            self._resolved_port = ""
            return ""
        preferred = next(
            (
                item
                for item in ports
                if any(token in f"{item.description} {item.manufacturer}".lower() for token in ["usb", "serial", "cp210", "wch", "ch340"])
            ),
            ports[0],
        )
        self._resolved_port = preferred.device
        return self._resolved_port

    @property
    def port(self) -> str:
        return self._resolved_port or self.resolve_port()

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._serial is not None and getattr(self._serial, "is_open", False)

    def open(self) -> bool:
        with self._lock:
            if self._serial is not None and getattr(self._serial, "is_open", False):
                return True
            if serial is None:
                return False
            path = self.resolve_port()
            if not path:
                return False
            self._serial = serial.Serial(path, self.baud, timeout=0.25, write_timeout=1)
            return True

    def close(self) -> None:
        with self._lock:
            if self._serial is None:
                return
            try:
                self._serial.close()
            finally:
                self._serial = None

    def send_line(self, line: str) -> None:
        if not self.open():
            raise RuntimeError("serial transport is unavailable")
        with self._lock:
            assert self._serial is not None
            self._serial.write(line.encode("utf-8"))
            self._serial.flush()

    def send_json(self, payload: dict) -> None:
        self.send_line(json.dumps(sanitize_device_payload(payload), ensure_ascii=True) + "\n")

    def read_line(self, timeout: float | None = None) -> str:
        if not self.open():
            return ""
        with self._lock:
            assert self._serial is not None
            previous_timeout = self._serial.timeout
            if timeout is not None:
                self._serial.timeout = timeout
            try:
                raw = self._serial.readline()
            finally:
                if timeout is not None and self._serial is not None:
                    self._serial.timeout = previous_timeout
        return raw.decode("utf-8", errors="replace").strip()

    def drain_lines(self, max_lines: int = 20) -> list[str]:
        lines: list[str] = []
        for _ in range(max_lines):
            line = self.read_line(timeout=0.05)
            if not line:
                break
            lines.append(line)
        return lines

    def send_handshake(self, owner_name: str, device_name: str) -> None:
        now = datetime.now().astimezone()
        tz_offset = int(now.utcoffset().total_seconds()) if now.utcoffset() else 0
        self.send_json({"time": [int(now.timestamp()), tz_offset]})
        if owner_name:
            self.send_json({"cmd": "owner", "name": owner_name})
        if device_name:
            self.send_json({"cmd": "name", "name": device_name})

    def request_status(self) -> dict | None:
        self.send_json({"cmd": "status"})
        for _ in range(12):
            line = self.read_line(timeout=0.25)
            if not line or not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("ack") == "status":
                return payload
        return None

    def __enter__(self) -> "SerialTransport":
        if not self.open():
            raise RuntimeError("serial transport is unavailable")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def discover_serial_devices() -> list[SerialDeviceInfo]:
    if list_ports is None:
        return []
    devices: list[SerialDeviceInfo] = []
    for port in list_ports.comports():
        devices.append(
            SerialDeviceInfo(
                device=getattr(port, "device", ""),
                description=getattr(port, "description", ""),
                manufacturer=getattr(port, "manufacturer", ""),
            )
        )
    return devices


def serial_summary(preferred_port: str = "") -> dict:
    transport = SerialTransport(port=preferred_port)
    return {
        "available": transport.available(),
        "selected_port": transport.port,
        "ports": [device.__dict__ for device in discover_serial_devices()],
    }


def send_bootstrap_and_heartbeat(port: str, baud: int, owner_name: str, device_name: str, heartbeat: dict) -> dict:
    with SerialTransport(port=port, baud=baud) as transport:
        transport.drain_lines()
        transport.send_handshake(owner_name=owner_name, device_name=device_name)
        transport.send_json(heartbeat)
        return {"ok": True, "port": transport.port}


def send_permission_decision(port: str, baud: int, request_id: str, decision: str) -> dict:
    with SerialTransport(port=port, baud=baud) as transport:
        transport.send_json({"cmd": "permission", "id": request_id, "decision": decision})
        return {"ok": True, "port": transport.port}


def request_device_status(port: str, baud: int) -> dict:
    with SerialTransport(port=port, baud=baud) as transport:
        return {"ok": True, "port": transport.port, "status": transport.request_status()}
