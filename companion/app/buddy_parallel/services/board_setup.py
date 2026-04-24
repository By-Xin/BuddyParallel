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
DEFAULT_BOARD_ID = "m5stickc-plus"
AUTO_BOARD_ID = "auto"


@dataclass(frozen=True)
class BoardProfile:
    id: str
    display_name: str
    pio_env: str
    firmware_subdir: str
    chip: str
    aliases: tuple[str, ...]
    bootloader_address: int = 0x1000
    partitions_address: int = 0x8000
    boot_app0_address: int | None = 0xE000
    firmware_address: int = 0x10000
    flash_mode: str = "dio"
    flash_freq: str = "40m"
    usb_vid_pid: tuple[tuple[int, int], ...] = ()
    detection_tokens: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return self.display_name


BOARD_PROFILES: tuple[BoardProfile, ...] = (
    BoardProfile(
        id="m5stickc-plus",
        display_name="M5StickC Plus",
        pio_env="m5stickc-plus",
        firmware_subdir="m5stickc-plus",
        chip="esp32",
        aliases=("m5stickc-plus", "m5stick", "m5stick-c", "stick", "stickc", "stickc-plus"),
        bootloader_address=0x1000,
        flash_mode="dio",
        flash_freq="40m",
        detection_tokens=("cp210", "ch340", "m5stick", "stickc"),
    ),
    BoardProfile(
        id="m5stack-cores3",
        display_name="M5Stack CoreS3",
        pio_env="m5stack-cores3",
        firmware_subdir="m5stack-cores3",
        chip="esp32s3",
        aliases=("m5stack-cores3", "m5stack-s3", "m5stacks3", "cores3", "core-s3", "s3"),
        bootloader_address=0x0,
        flash_mode="dio",
        flash_freq="80m",
        usb_vid_pid=((0x303A, 0x8119),),
        detection_tokens=("cores3", "core s3", "usb jtag/serial", "usb jtag", "esp32-s3", "esp32s3"),
    ),
)


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
    profile: BoardProfile

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
    hwid: str = ""
    vid: int | None = None
    pid: int | None = None
    inferred_board_id: str = ""
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
    board_id: str = ""
    status: dict | None = None


class FirmwareFlashError(RuntimeError):
    pass


ProgressCallback = Callable[[str], None]
EsptoolRunner = Callable[[list[str], ProgressCallback | None], int]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def supported_board_profiles() -> tuple[BoardProfile, ...]:
    return BOARD_PROFILES


def normalize_board_id(board_id: str = AUTO_BOARD_ID) -> str:
    text = str(board_id or AUTO_BOARD_ID).strip().lower()
    if text in {"", AUTO_BOARD_ID}:
        return AUTO_BOARD_ID
    for profile in BOARD_PROFILES:
        if text == profile.id or text in profile.aliases:
            return profile.id
    raise ValueError(f"Unsupported board type: {board_id}")


def get_board_profile(board_id: str = DEFAULT_BOARD_ID) -> BoardProfile:
    normalized = normalize_board_id(board_id)
    if normalized == AUTO_BOARD_ID:
        normalized = DEFAULT_BOARD_ID
    for profile in BOARD_PROFILES:
        if profile.id == normalized:
            return profile
    raise ValueError(f"Unsupported board type: {board_id}")


def board_label(board_id: str) -> str:
    return get_board_profile(board_id).display_name


def infer_board_profile(device: SerialDeviceInfo | BoardCandidate | None) -> BoardProfile | None:
    if device is None:
        return None
    vid = getattr(device, "vid", None)
    pid = getattr(device, "pid", None)
    if vid is not None and pid is not None:
        for profile in BOARD_PROFILES:
            if (int(vid), int(pid)) in profile.usb_vid_pid:
                return profile
    haystack = " ".join(
        str(getattr(device, key, "") or "")
        for key in ("description", "manufacturer", "hwid", "serial_number")
    ).lower()
    for profile in BOARD_PROFILES:
        if any(token in haystack for token in profile.detection_tokens):
            return profile
    return None


def choose_board_profile(board_id: str = AUTO_BOARD_ID, port: str = "", candidates: list[BoardCandidate] | None = None) -> BoardProfile:
    normalized = normalize_board_id(board_id)
    if normalized != AUTO_BOARD_ID:
        return get_board_profile(normalized)
    candidates = candidates if candidates is not None else list_board_candidates(probe_status=False)
    if port:
        selected = next((candidate for candidate in candidates if candidate.port == port), None)
        inferred = infer_board_profile(selected)
        if inferred is not None:
            return inferred
    for candidate in candidates:
        inferred = infer_board_profile(candidate)
        if inferred is not None:
            return inferred
    return get_board_profile(DEFAULT_BOARD_ID)


def default_firmware_roots(board_id: str = DEFAULT_BOARD_ID) -> list[Path]:
    profile = get_board_profile(board_id)
    roots: list[Path] = []
    override = os.environ.get(FIRMWARE_ENV_VAR, "").strip()
    if override:
        roots.append(Path(override).expanduser())

    if getattr(sys, "frozen", False):
        internal_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        roots.append(internal_root / "firmware" / profile.firmware_subdir)
        roots.append(internal_root / "firmware")
        roots.append(Path(sys.executable).resolve().parent / "firmware" / profile.firmware_subdir)
        roots.append(Path(sys.executable).resolve().parent / "firmware")

    root = repo_root()
    roots.extend(
        [
            root / "dist" / "BuddyParallel" / "firmware" / profile.firmware_subdir,
            root / "dist" / "BuddyParallel" / "firmware",
            root / "companion" / "app" / "buddy_parallel" / "assets" / "firmware" / profile.firmware_subdir,
            root / "companion" / "app" / "buddy_parallel" / "assets" / "firmware",
            root / "firmware" / ".pio" / "build" / profile.pio_env,
        ]
    )
    return _dedupe_paths(roots)


def find_firmware_bundle(root: Path | str | None = None, board_id: str = DEFAULT_BOARD_ID) -> FirmwareBundle:
    profile = get_board_profile(board_id)
    if root is not None:
        return _bundle_from_root(Path(root).expanduser(), profile)

    candidates = default_firmware_roots(profile.id)
    for candidate in candidates:
        bundle = _bundle_from_root(candidate, profile)
        if bundle.available:
            return bundle
    if candidates:
        return _bundle_from_root(candidates[0], profile)
    return _bundle_from_root(Path("firmware"), profile)


def list_board_candidates(baud: int = DEFAULT_SERIAL_BAUD, probe_status: bool = True) -> list[BoardCandidate]:
    candidates: list[BoardCandidate] = []
    for device in discover_serial_devices():
        status: dict | None = None
        error = ""
        inferred = infer_board_profile(device)
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
                hwid=device.hwid,
                vid=device.vid,
                pid=device.pid,
                inferred_board_id=inferred.id if inferred is not None else "",
                status=status,
                error=error,
            )
        )
    return candidates


def choose_board_port(preferred_port: str = "", baud: int = DEFAULT_SERIAL_BAUD, board_id: str = AUTO_BOARD_ID) -> str:
    preferred_port = preferred_port.strip()
    if preferred_port:
        return preferred_port

    candidates = list_board_candidates(baud=baud, probe_status=True)
    buddy = next((candidate for candidate in candidates if candidate.is_buddy_parallel), None)
    if buddy is not None:
        return buddy.port

    profile = choose_board_profile(board_id, candidates=candidates)
    profile_match = next((candidate for candidate in candidates if candidate.inferred_board_id == profile.id), None)
    if profile_match is not None:
        return profile_match.port

    devices = [_serial_info_from_candidate(candidate) for candidate in candidates]
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
    profile = bundle.profile
    return [
        "--chip",
        profile.chip,
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
        profile.flash_mode,
        "--flash_freq",
        profile.flash_freq,
        "--flash_size",
        "detect",
        *bundle.esptool_segments(),
    ]


def build_erase_flash_args(port: str, flash_baud: int = DEFAULT_FLASH_BAUD, board_id: str = DEFAULT_BOARD_ID) -> list[str]:
    profile = get_board_profile(board_id)
    return [
        "--chip",
        profile.chip,
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
    board_id: str = AUTO_BOARD_ID,
    erase_first: bool = False,
    flash_baud: int = DEFAULT_FLASH_BAUD,
    serial_baud: int = DEFAULT_SERIAL_BAUD,
    progress: ProgressCallback | None = None,
    runner: EsptoolRunner | None = None,
) -> FlashResult:
    candidates = list_board_candidates(baud=serial_baud, probe_status=False)
    profile = choose_board_profile(board_id, port=port.strip(), candidates=candidates)
    bundle = find_firmware_bundle(firmware_root, board_id=profile.id)
    if not bundle.available:
        missing = ", ".join(str(path) for path in bundle.missing_files)
        return FlashResult(False, port, f"{profile.display_name} firmware bundle is incomplete: {missing}", bundle.root, profile.id)

    selected_port = choose_board_port(port, baud=serial_baud, board_id=profile.id)
    if not selected_port:
        return FlashResult(False, "", f"No serial board was found for {profile.display_name}.", bundle.root, profile.id)

    runner = runner or run_esptool
    if erase_first:
        _emit(progress, f"Erasing {profile.display_name} flash...")
        _check_esptool_exit(runner(build_erase_flash_args(selected_port, flash_baud, profile.id), progress))

    _emit(progress, f"Flashing BuddyParallel firmware for {profile.display_name} on {selected_port}...")
    _check_esptool_exit(runner(build_write_flash_args(selected_port, bundle, flash_baud), progress))
    _emit(progress, "Waiting for the board to reboot...")
    status = wait_for_board_status(selected_port, baud=serial_baud)
    if status is None:
        return FlashResult(
            False,
            selected_port,
            f"{profile.display_name} firmware was written, but BuddyParallel did not answer after reboot.",
            bundle.root,
            profile.id,
            status,
        )
    return FlashResult(True, selected_port, f"BuddyParallel firmware is ready on {profile.display_name}.", bundle.root, profile.id, status)


def save_board_port(port: str, config_store: ConfigStore | None = None, board_id: str = AUTO_BOARD_ID) -> AppConfig:
    store = config_store or ConfigStore()
    config = store.load()
    profile_id = normalize_board_id(board_id)
    updated = replace(config, transport_mode="auto", serial_port=port.strip(), serial_baud=DEFAULT_SERIAL_BAUD, board_profile=profile_id)
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


def _bundle_from_root(root: Path, profile: BoardProfile) -> FirmwareBundle:
    boot_app0 = root / "boot_app0.bin"
    if profile.boot_app0_address is not None and not boot_app0.exists():
        local_boot_app0 = repo_root() / "firmware" / ".platformio_local" / "packages" / "framework-arduinoespressif32" / "tools" / "partitions" / "boot_app0.bin"
        if local_boot_app0.exists():
            boot_app0 = local_boot_app0

    images = [
        FirmwareImage("bootloader", profile.bootloader_address, root / "bootloader.bin"),
        FirmwareImage("partitions", profile.partitions_address, root / "partitions.bin"),
    ]
    if profile.boot_app0_address is not None:
        images.append(FirmwareImage("boot_app0", profile.boot_app0_address, boot_app0))
    images.append(FirmwareImage("firmware", profile.firmware_address, root / "firmware.bin"))
    return FirmwareBundle(root=root, images=tuple(images), profile=profile)


def _serial_info_from_candidate(candidate: BoardCandidate) -> SerialDeviceInfo:
    return SerialDeviceInfo(
        candidate.port,
        candidate.description,
        candidate.manufacturer,
        candidate.hwid,
        candidate.vid,
        candidate.pid,
    )


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
