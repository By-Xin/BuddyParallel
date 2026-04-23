from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ASCII_PET_NAMES = (
    "capybara",
    "duck",
    "goose",
    "blob",
    "cat",
    "dragon",
    "octopus",
    "owl",
    "penguin",
    "turtle",
    "snail",
    "ghost",
    "axolotl",
    "cactus",
    "robot",
    "rabbit",
    "mushroom",
    "chonk",
)
GIF_PET_INDEX = 0xFF


@dataclass(frozen=True)
class HardwareSnapshot:
    connected: bool = False
    name: str = ""
    owner: str = ""
    battery_pct: int | None = None
    usb_powered: bool = False
    brightness: int | None = None
    sound_enabled: bool | None = None
    led_enabled: bool | None = None
    pet_index: int | None = None
    pet_name: str = ""
    pet_mode: str = ""
    gif_available: bool = False


def parse_hardware_snapshot(payload: dict[str, Any] | None) -> HardwareSnapshot:
    if not isinstance(payload, dict):
        return HardwareSnapshot()

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return HardwareSnapshot()

    bat = data.get("bat") if isinstance(data.get("bat"), dict) else {}
    settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
    pet = data.get("pet") if isinstance(data.get("pet"), dict) else {}

    pet_mode = str(pet.get("mode") or "").strip().lower()
    pet_index = _coerce_int(pet.get("index"))
    if pet_mode == "gif" and pet_index is None:
        pet_index = GIF_PET_INDEX
    pet_name = str(pet.get("name") or "").strip().lower()
    if not pet_name and pet_index is not None:
        pet_name = pet_name_for_index(pet_index)

    return HardwareSnapshot(
        connected=bool(data),
        name=str(data.get("name") or "").strip(),
        owner=str(data.get("owner") or "").strip(),
        battery_pct=_coerce_int(bat.get("pct")),
        usb_powered=_coerce_bool(bat.get("usb"), default=False),
        brightness=_coerce_int(settings.get("brightness")),
        sound_enabled=_coerce_optional_bool(settings.get("sound")),
        led_enabled=_coerce_optional_bool(settings.get("led")),
        pet_index=pet_index,
        pet_name=pet_name,
        pet_mode=pet_mode,
        gif_available=_coerce_bool(pet.get("gif_available"), default=False),
    )


def pet_name_for_index(index: int | None) -> str:
    if index is None:
        return ""
    if index == GIF_PET_INDEX:
        return "gif"
    if 0 <= index < len(ASCII_PET_NAMES):
        return ASCII_PET_NAMES[index]
    return ""


def pet_display_name(name: str) -> str:
    normalized = str(name or "").strip().lower()
    if not normalized:
        return "Unknown"
    if normalized == "gif":
        return "GIF Character"
    return normalized.replace("_", " ").title()


def brightness_display(level: int | None) -> str:
    return f"{level}/4" if level is not None else "?"


def pet_choices(snapshot: HardwareSnapshot | None = None) -> list[tuple[int, str]]:
    options = [(index, pet_display_name(name)) for index, name in enumerate(ASCII_PET_NAMES)]
    if snapshot is not None and snapshot.gif_available:
        options.append((GIF_PET_INDEX, "GIF Character"))
    return options


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text and text.lstrip("-").isdigit():
            return int(text)
    return None


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return _coerce_bool(value, default=False)
