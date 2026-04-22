from __future__ import annotations

from buddy_parallel.transports.base import TransportBase

NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


class BleTransport(TransportBase):
    def __init__(self, device_name: str = "") -> None:
        super().__init__(name="ble")
        self.device_name = device_name

    def available(self) -> bool:
        return False

    def send_line(self, line: str) -> None:
        raise NotImplementedError("BLE transport is scaffolded but not yet implemented")
