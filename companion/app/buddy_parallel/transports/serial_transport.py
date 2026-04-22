from __future__ import annotations

from buddy_parallel.transports.base import TransportBase

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None


class SerialTransport(TransportBase):
    def __init__(self, port: str = "", baud: int = 115200) -> None:
        super().__init__(name="serial")
        self.port = port
        self.baud = baud

    def available(self) -> bool:
        if serial is None:
            return False
        return self._pick_port() is not None

    def _pick_port(self) -> str | None:
        if self.port:
            return self.port
        if list_ports is None:
            return None
        ports = list(list_ports.comports())
        return ports[0].device if ports else None

    def send_line(self, line: str) -> None:
        if serial is None:
            raise RuntimeError("pyserial not installed")
        path = self._pick_port()
        if not path:
            raise RuntimeError("no serial port available")
        ser = serial.Serial(path, self.baud, timeout=1)
        try:
            ser.write(line.encode("utf-8"))
        finally:
            ser.close()
