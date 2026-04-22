from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class DeviceTransport(Protocol):
    name: str

    def available(self) -> bool: ...

    def send_json(self, payload: dict) -> None: ...


@dataclass
class DeviceManager:
    transports: list[DeviceTransport]
    active_name: str = ""

    def active_transport(self) -> DeviceTransport | None:
        for transport in self.transports:
            if transport.name == self.active_name and transport.available():
                return transport
        for transport in self.transports:
            if transport.available():
                self.active_name = transport.name
                return transport
        return None

    def send(self, payload: dict) -> bool:
        transport = self.active_transport()
        if transport is None:
            return False
        transport.send_json(payload)
        return True
