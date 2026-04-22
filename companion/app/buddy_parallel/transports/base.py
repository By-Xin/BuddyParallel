from __future__ import annotations

import json
from dataclasses import dataclass

UNSUPPORTED_TEXT_PLACEHOLDER = "(>_<) beep beep"


def sanitize_device_text(value: str) -> str:
    raw = str(value or "")
    ascii_chars: list[str] = []
    had_unsupported = False
    for char in raw:
        if char in "\r\n\t":
            ascii_chars.append(" ")
            continue
        if 32 <= ord(char) <= 126:
            ascii_chars.append(char)
            continue
        had_unsupported = True
    sanitized = " ".join("".join(ascii_chars).split())
    if sanitized:
        return f"{sanitized} ^_^ beep beep" if had_unsupported else sanitized
    return UNSUPPORTED_TEXT_PLACEHOLDER if had_unsupported else ""


def sanitize_device_payload(value):
    if isinstance(value, str):
        return sanitize_device_text(value)
    if isinstance(value, list):
        return [sanitize_device_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_device_payload(item) for key, item in value.items()}
    return value


@dataclass
class TransportBase:
    name: str

    def available(self) -> bool:
        return False

    def send_json(self, payload: dict) -> None:
        self.send_line(json.dumps(sanitize_device_payload(payload), ensure_ascii=True) + "\n")

    def send_line(self, line: str) -> None:
        raise NotImplementedError
