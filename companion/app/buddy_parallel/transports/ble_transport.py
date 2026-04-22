from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from datetime import datetime
from queue import Empty, Queue

from buddy_parallel.transports.base import TransportBase

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    BleakClient = None
    BleakScanner = None

NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
DEFAULT_NAME_PREFIXES = ("Claude-", "BuddyParallel")


@dataclass
class BleDeviceInfo:
    address: str
    name: str = ""


class BleTransport(TransportBase):
    def __init__(self, device_name: str = "") -> None:
        super().__init__(name="ble")
        self.device_name = device_name.strip()
        self._device: BleDeviceInfo | None = None
        self._client = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._lock = threading.RLock()
        self._rx_queue: Queue[str] = Queue()
        self._notify_buffer = bytearray()

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._client is not None and bool(getattr(self._client, "is_connected", False))

    @property
    def address(self) -> str:
        return self._device.address if self._device else ""

    @property
    def connected_name(self) -> str:
        return self._device.name if self._device else self.device_name

    def available(self) -> bool:
        if BleakScanner is None:
            return False
        if self.is_open:
            return True
        return self.resolve_device() is not None

    def resolve_device(self) -> BleDeviceInfo | None:
        if BleakScanner is None:
            return None
        if self._device is not None:
            return self._device
        self._ensure_loop()
        device = self._run_async(self._discover_device())
        if device is not None:
            self._device = device
        return device

    def open(self) -> bool:
        if BleakClient is None:
            return False
        if self.is_open:
            return True
        self._ensure_loop()
        return bool(self._run_async(self._async_open(), timeout=20.0))

    def close(self) -> None:
        if self._loop is None:
            return
        try:
            self._run_async(self._async_close(), timeout=10.0)
        except Exception:
            pass
        self._shutdown_loop()

    def send_line(self, line: str) -> None:
        if not self.open():
            raise RuntimeError("BLE transport is unavailable")
        self._run_async(self._async_write(line.encode("utf-8")), timeout=10.0)

    def send_json(self, payload: dict) -> None:
        self.send_line(json.dumps(payload, ensure_ascii=False) + "\n")

    def read_line(self, timeout: float | None = None) -> str:
        wait_timeout = 0 if timeout is None else timeout
        try:
            return self._rx_queue.get(timeout=wait_timeout)
        except Empty:
            return ""

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
            line = self.read_line(timeout=0.5)
            if not line or not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("ack") == "status":
                return payload
        return None

    def __enter__(self) -> "BleTransport":
        if not self.open():
            raise RuntimeError("BLE transport is unavailable")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _ensure_loop(self) -> None:
        if self._thread is not None and self._thread.is_alive() and self._loop is not None:
            return
        self._ready.clear()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop_main, name="ble-transport", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)

    def _loop_main(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def _shutdown_loop(self) -> None:
        loop = self._loop
        thread = self._thread
        self._loop = None
        self._thread = None
        self._ready.clear()
        if loop is None:
            return
        loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=2.0)
        loop.close()

    def _run_async(self, coro, timeout: float = 10.0):
        if self._loop is None:
            raise RuntimeError("BLE event loop is not running")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    async def _discover_device(self) -> BleDeviceInfo | None:
        assert BleakScanner is not None
        devices = await BleakScanner.discover(timeout=4.0)
        exact: BleDeviceInfo | None = None
        prefix_matches: list[BleDeviceInfo] = []
        for device in devices:
            name = getattr(device, "name", "") or ""
            address = getattr(device, "address", "") or ""
            info = BleDeviceInfo(address=address, name=name)
            if self.device_name:
                if address.lower() == self.device_name.lower() or name.lower() == self.device_name.lower():
                    exact = info
                    break
                if name.lower().startswith(self.device_name.lower()):
                    prefix_matches.append(info)
            elif any(name.startswith(prefix) for prefix in DEFAULT_NAME_PREFIXES):
                prefix_matches.append(info)
        return exact or (prefix_matches[0] if prefix_matches else None)

    async def _async_open(self) -> bool:
        assert BleakClient is not None
        device = self._device or await self._discover_device()
        if device is None:
            return False
        self._device = device
        if self._client is not None and getattr(self._client, "is_connected", False):
            return True
        client = BleakClient(device.address, timeout=10.0)
        await client.connect()
        if not getattr(client, "is_connected", False):
            return False
        await client.start_notify(NUS_TX_UUID, self._handle_notification)
        with self._lock:
            self._client = client
            self._notify_buffer = bytearray()
            while not self._rx_queue.empty():
                try:
                    self._rx_queue.get_nowait()
                except Empty:
                    break
        return True

    async def _async_close(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            await client.stop_notify(NUS_TX_UUID)
        except Exception:
            pass
        try:
            await client.disconnect()
        except Exception:
            pass

    async def _async_write(self, payload: bytes) -> None:
        client = self._client
        if client is None or not getattr(client, "is_connected", False):
            raise RuntimeError("BLE transport is unavailable")
        await client.write_gatt_char(NUS_RX_UUID, payload, response=False)

    def _handle_notification(self, _characteristic, data: bytearray) -> None:
        with self._lock:
            self._notify_buffer.extend(bytes(data))
            while b"\n" in self._notify_buffer:
                raw, _, remaining = self._notify_buffer.partition(b"\n")
                self._notify_buffer = bytearray(remaining)
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    self._rx_queue.put(line)


def ble_summary(preferred_name: str = "") -> dict:
    transport = BleTransport(device_name=preferred_name)
    device = transport.resolve_device() if BleakScanner is not None else None
    return {
        "installed": BleakScanner is not None,
        "available": device is not None,
        "selected_name": device.name if device else "",
        "selected_address": device.address if device else "",
    }
