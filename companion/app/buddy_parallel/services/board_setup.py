from __future__ import annotations

import contextlib
import io
import os
import sys
import time
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Callable

from buddy_parallel.runtime.config import AppConfig, ConfigStore
from buddy_parallel.transports.serial_transport import SerialDeviceInfo, SerialTransport, discover_serial_devices


DEFAULT_FLASH_BAUD = 115200
DEFAULT_SERIAL_BAUD = 115200
FIRMWARE_ENV_VAR = "BUDDY_PARALLEL_FIRMWARE_DIR"


@dataclass(frozen=True)
class FirmwareImage:
    name: str
    address: int
    path: Path

    @property
    def address_arg(self) -> str:
        return f"0x{self.address:x}"


@dataclass(frozen=True)
class FirmwareBundle:
    root: Path
    images: tuple[FirmwareImage, ...]

    @property
    def available(self) -> bool:
        return not self.missing_files

    @property
    def missing_files(self) -> tuple[Path, ...]:
        return tuple(image.path for image in self.images if not image.path.exists())

    def esptool_segments(self) -> list[str]:
        segments: list[str] = []
        for image in self.images:
            segments.extend([image.address_arg, str(image.path)])
        return segments


@dataclass(frozen=True)
class BoardCandidate:
    port: str
    description: str = ""
    manufacturer: str = ""
    status: dict | None = None
    error: str = ""

    @property
    def is_buddy_parallel(self) -> bool:
        return self.status is not None

    @property
    def label(self) -> str:
        detail = " ".join(part for part in [self.description, self.manufacturer] if part).strip()
        return f"{self.port} | {detail}" if detail else self.port


@dataclass(frozen=True)
class FlashResult:
    ok: bool
    port: str
    message: str
    bundle_root: Path | None = None
    status: dict | None = None


class FirmwareFlashError(RuntimeError):
    pass


ProgressCallback = Callable[[str], None]
EsptoolRunner = Callable[[list[str], ProgressCallback | None], int]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_firmware_roots() -> list[Path]:
    roots: list[Path] = []
    override = os.environ.get(FIRMWARE_ENV_VAR, "").strip()
    if override:
        roots.append(Path(override).expanduser())

    if getattr(sys, "frozen", False):
        internal_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        roots.append(internal_root / "firmware")
        roots.append(Path(sys.executable).resolve().parent / "firmware")

    root = repo_root()
    roots.extend(
        [
            root / "dist" / "BuddyParallel" / "firmware",
            root / "companion" / "app" / "buddy_parallel" / "assets" / "firmware",
            root / "firmware" / ".pio" / "build" / "m5stickc-plus",
        ]
    )
    return _dedupe_paths(roots)


def find_firmware_bundle(root: Path | str | None = None) -> FirmwareBundle:
    if root is not None:
        return _bundle_from_root(Path(root).expanduser())

    candidates = default_firmware_roots()
    for candidate in candidates:
        bundle = _bundle_from_root(candidate)
        if bundle.available:
            return bundle
    if candidates:
        return _bundle_from_root(candidates[0])
    return _bundle_from_root(Path("firmware"))


def list_board_candidates(baud: int = DEFAULT_SERIAL_BAUD, probe_status: bool = True) -> list[BoardCandidate]:
    candidates: list[BoardCandidate] = []
    for device in discover_serial_devices():
        status: dict | None = None
        error = ""
        if probe_status:
            try:
                status = request_board_status(device.device, baud=baud)
            except Exception as exc:
                error = str(exc)
        candidates.append(
            BoardCandidate(
                port=device.device,
                description=device.description,
                manufacturer=device.manufacturer,
                status=status,
                error=error,
            )
        )
    return candidates


def choose_board_port(preferred_port: str = "", baud: int = DEFAULT_SERIAL_BAUD) -> str:
    preferred_port = preferred_port.strip()
    if preferred_port:
        return preferred_port

    candidates = list_board_candidates(baud=baud, probe_status=True)
    buddy = next((candidate for candidate in candidates if candidate.is_buddy_parallel), None)
    if buddy is not None:
        return buddy.port

    devices = [
        SerialDeviceInfo(candidate.port, candidate.description, candidate.manufacturer)
        for candidate in candidates
    ]
    preferred = _preferred_serial_device(devices)
    return preferred.device if preferred is not None else ""


def request_board_status(port: str, baud: int = DEFAULT_SERIAL_BAUD) -> dict | None:
    if not port:
        return None
    with SerialTransport(port=port, baud=baud) as transport:
        transport.drain_lines()
        return transport.request_status()


def wait_for_board_status(port: str, baud: int = DEFAULT_SERIAL_BAUD, timeout_seconds: float = 12.0) -> dict | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            status = request_board_status(port, baud=baud)
            if status is not None:
                return status
        except Exception:
            pass
        time.sleep(0.5)
    return None


def build_write_flash_args(port: str, bundle: FirmwareBundle, flash_baud: int = DEFAULT_FLASH_BAUD) -> list[str]:
    return [
        "--chip",
        "esp32",
        "--port",
        port,
        "--baud",
        str(flash_baud),
        "--before",
        "default_reset",
        "--after",
        "hard_reset",
        "write_flash",
        "-z",
        "--flash_mode",
        "dio",
        "--flash_freq",
        "40m",
        "--flash_size",
        "detect",
        *bundle.esptool_segments(),
    ]


def build_erase_flash_args(port: str, flash_baud: int = DEFAULT_FLASH_BAUD) -> list[str]:
    return [
        "--chip",
        "esp32",
        "--port",
        port,
        "--baud",
        str(flash_baud),
        "--before",
        "default_reset",
        "--after",
        "hard_reset",
        "erase_flash",
    ]


def flash_board(
    port: str = "",
    firmware_root: Path | str | None = None,
    *,
    erase_first: bool = False,
    flash_baud: int = DEFAULT_FLASH_BAUD,
    serial_baud: int = DEFAULT_SERIAL_BAUD,
    progress: ProgressCallback | None = None,
    runner: EsptoolRunner | None = None,
) -> FlashResult:
    bundle = find_firmware_bundle(firmware_root)
    if not bundle.available:
        missing = ", ".join(str(path) for path in bundle.missing_files)
        return FlashResult(False, port, f"Firmware bundle is incomplete: {missing}", bundle.root)

    selected_port = choose_board_port(port, baud=serial_baud)
    if not selected_port:
        return FlashResult(False, "", "No serial board was found.", bundle.root)

    runner = runner or run_esptool
    if erase_first:
        _emit(progress, "Erasing board flash...")
        _check_esptool_exit(runner(build_erase_flash_args(selected_port, flash_baud), progress))

    _emit(progress, f"Flashing BuddyParallel firmware on {selected_port}...")
    _check_esptool_exit(runner(build_write_flash_args(selected_port, bundle, flash_baud), progress))
    _emit(progress, "Waiting for the board to reboot...")
    status = wait_for_board_status(selected_port, baud=serial_baud)
    if status is None:
        return FlashResult(
            False,
            selected_port,
            "Firmware was written, but BuddyParallel did not answer after reboot.",
            bundle.root,
            status,
        )
    return FlashResult(True, selected_port, "BuddyParallel firmware is ready.", bundle.root, status)


def save_board_port(port: str, config_store: ConfigStore | None = None) -> AppConfig:
    store = config_store or ConfigStore()
    config = store.load()
    updated = replace(config, transport_mode="auto", serial_port=port.strip(), serial_baud=DEFAULT_SERIAL_BAUD)
    store.save(updated)
    return updated


def run_esptool(args: list[str], progress: ProgressCallback | None = None) -> int:
    try:
        import esptool
    except ImportError as exc:
        raise FirmwareFlashError("esptool is not installed in this BuddyParallel build.") from exc

    buffer = _ProgressBuffer(progress)
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        try:
            result = esptool.main(args)
        except SystemExit as exc:
            return int(exc.code or 0)
    return int(result or 0)


def _check_esptool_exit(exit_code: int) -> None:
    if exit_code != 0:
        raise FirmwareFlashError(f"esptool failed with exit code {exit_code}.")


def _bundle_from_root(root: Path) -> FirmwareBundle:
    boot_app0 = root / "boot_app0.bin"
    if not boot_app0.exists():
        local_boot_app0 = repo_root() / "firmware" / ".platformio_local" / "packages" / "framework-arduinoespressif32" / "tools" / "partitions" / "boot_app0.bin"
        if local_boot_app0.exists():
            boot_app0 = local_boot_app0

    images = (
        FirmwareImage("bootloader", 0x1000, root / "bootloader.bin"),
        FirmwareImage("partitions", 0x8000, root / "partitions.bin"),
        FirmwareImage("boot_app0", 0xE000, boot_app0),
        FirmwareImage("firmware", 0x10000, root / "firmware.bin"),
    )
    return FirmwareBundle(root=root, images=images)


def _preferred_serial_device(devices: list[SerialDeviceInfo]) -> SerialDeviceInfo | None:
    if not devices:
        return None
    preferred = next(
        (
            item
            for item in devices
            if any(token in f"{item.description} {item.manufacturer}".lower() for token in ["usb", "serial", "cp210", "wch", "ch340"])
        ),
        None,
    )
    return preferred or devices[0]


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve() if path.exists() else path.absolute()).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


class _ProgressBuffer(io.TextIOBase):
    def __init__(self, progress: ProgressCallback | None) -> None:
        self._progress = progress
        self._pending = ""

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        if not value:
            return 0
        if self._progress is None:
            return len(value)
        self._pending += value
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            line = line.strip()
            if line:
                self._progress(line)
        return len(value)

    def flush(self) -> None:
        if self._progress is not None and self._pending.strip():
            self._progress(self._pending.strip())
        self._pending = ""
