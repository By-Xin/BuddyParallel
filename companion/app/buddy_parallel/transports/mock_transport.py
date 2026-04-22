from __future__ import annotations

from buddy_parallel.transports.base import TransportBase


class MockTransport(TransportBase):
    def __init__(self) -> None:
        super().__init__(name="mock")
        self.lines: list[str] = []

    def available(self) -> bool:
        return True

    def send_line(self, line: str) -> None:
        self.lines.append(line)
