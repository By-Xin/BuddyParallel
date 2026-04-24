from __future__ import annotations

import shutil
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from buddy_parallel.services import board_setup
from buddy_parallel.transports.serial_transport import SerialDeviceInfo


TEST_TMP = Path(__file__).resolve().parents[1] / "tmp-board-setup-tests"


@contextmanager
def _temporary_directory():
    TEST_TMP.mkdir(parents=True, exist_ok=True)
    root = TEST_TMP / f"case-{uuid.uuid4().hex}"
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _make_firmware_bundle(root: Path) -> None:
    for name in ("bootloader.bin", "partitions.bin", "boot_app0.bin", "firmware.bin"):
        (root / name).write_bytes(b"bin")


class BoardSetupTests(unittest.TestCase):
    def test_find_firmware_bundle_builds_expected_flash_segments(self) -> None:
        with _temporary_directory() as root:
            _make_firmware_bundle(root)

            bundle = board_setup.find_firmware_bundle(root)
            available = bundle.available
            args = board_setup.build_write_flash_args("COM7", bundle, flash_baud=921600)

        self.assertTrue(available)
        self.assertIn("write_flash", args)
        self.assertIn("--baud", args)
        self.assertIn("921600", args)
        self.assertEqual(
            [args[index] for index in range(args.index("0x1000"), len(args), 2)],
            ["0x1000", "0x8000", "0xe000", "0x10000"],
        )

    def test_choose_board_port_prefers_existing_buddy_firmware(self) -> None:
        devices = [
            SerialDeviceInfo("COM3", "Bluetooth Serial", "Windows"),
            SerialDeviceInfo("COM7", "USB Serial", "Silicon Labs"),
        ]

        def fake_status(port: str, baud: int = 115200):
            return {"ack": "status"} if port == "COM7" else None

        with patch.object(board_setup, "discover_serial_devices", return_value=devices), patch.object(
            board_setup,
            "request_board_status",
            side_effect=fake_status,
        ):
            self.assertEqual(board_setup.choose_board_port(), "COM7")

    def test_flash_board_uses_runner_and_saves_success_status(self) -> None:
        calls: list[list[str]] = []
        progress: list[str] = []

        def runner(args: list[str], callback):
            calls.append(args)
            if callback is not None:
                callback("runner ok")
            return 0

        with _temporary_directory() as root:
            _make_firmware_bundle(root)
            with patch.object(board_setup, "choose_board_port", return_value="COM9"), patch.object(
                board_setup,
                "wait_for_board_status",
                return_value={"ack": "status"},
            ):
                result = board_setup.flash_board(
                    firmware_root=root,
                    runner=runner,
                    progress=progress.append,
                )

        self.assertTrue(result.ok)
        self.assertEqual(result.port, "COM9")
        self.assertEqual(len(calls), 1)
        self.assertIn("write_flash", calls[0])
        self.assertIn("runner ok", progress)

    def test_default_flash_baud_favors_reliable_beta_flashing(self) -> None:
        self.assertEqual(board_setup.DEFAULT_FLASH_BAUD, 115200)


if __name__ == "__main__":
    unittest.main()
