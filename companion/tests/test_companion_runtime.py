from __future__ import annotations

import logging
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buddy_parallel.core.companion_runtime import CompanionRuntime
from buddy_parallel.runtime.config import AppConfig
from buddy_parallel.runtime.state import StateStore


class _FakeSerialTransport:
    def __init__(self) -> None:
        self.name = "serial"
        self.port = "COM_TEST"
        self.is_open = False
        self.available_calls = 0
        self.open_calls = 0
        self.handshakes: list[tuple[str, str]] = []
        self.sent_payloads: list[dict] = []

    def available(self) -> bool:
        self.available_calls += 1
        return True

    def open(self) -> bool:
        self.open_calls += 1
        self.is_open = True
        return True

    def close(self) -> None:
        self.is_open = False

    def drain_lines(self, max_lines: int = 20) -> list[str]:
        return []

    def send_handshake(self, owner_name: str, device_name: str) -> None:
        self.handshakes.append((owner_name, device_name))

    def send_json(self, payload: dict) -> None:
        self.sent_payloads.append(payload)


class CompanionRuntimeTests(unittest.TestCase):
    def test_ensure_serial_session_bootstraps_without_sync_status_wait(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(dir=Path.cwd()))
        try:
            test_logger = logging.getLogger("buddy_parallel_test")
            with patch("buddy_parallel.core.companion_runtime.configure_logging", return_value=test_logger), patch(
                "buddy_parallel.ingest.hook_server.configure_logging",
                return_value=test_logger,
            ):
                runtime = CompanionRuntime(
                    config=AppConfig(transport_mode="serial", owner_name="Zhiyun", device_name="Buddy"),
                    state_store=StateStore(temp_dir / "state.json"),
                )
            fake_serial = _FakeSerialTransport()
            runtime._serial = fake_serial

            with patch("buddy_parallel.core.companion_runtime.sleep") as mocked_sleep:
                ready = runtime._ensure_serial_session()

            self.assertTrue(ready)
            self.assertEqual(mocked_sleep.call_count, 1)
            self.assertEqual(mocked_sleep.call_args.args[0], 1.5)
            self.assertEqual(fake_serial.open_calls, 1)
            self.assertEqual(fake_serial.handshakes, [("Zhiyun", "Buddy")])
            self.assertEqual(fake_serial.sent_payloads, [{"cmd": "status"}])
            self.assertTrue(runtime._serial_bootstrapped)
            self.assertEqual(runtime.device_manager.active_name, "serial")
            self.assertIsNone(runtime.latest_device_status())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
