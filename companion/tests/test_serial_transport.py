from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from buddy_parallel.transports import serial_transport


class SerialDiscoveryTests(unittest.TestCase):
    def test_discover_serial_devices_filters_bluetooth_virtual_ports(self) -> None:
        fake_ports = [
            SimpleNamespace(
                device="COM5",
                description="蓝牙链接上的标准串行",
                manufacturer="Microsoft",
                hwid="BTHENUM\\example",
            ),
            SimpleNamespace(
                device="COM7",
                description="USB Serial Device",
                manufacturer="Silicon Labs",
                hwid="USB VID:PID=10C4:EA60",
            ),
        ]

        with patch.object(serial_transport.list_ports, "comports", return_value=fake_ports):
            devices = serial_transport.discover_serial_devices()

        self.assertEqual([device.device for device in devices], ["COM7"])


if __name__ == "__main__":
    unittest.main()
