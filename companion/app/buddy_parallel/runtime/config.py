from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

APP_DIR = Path.home() / "AppData" / "Roaming" / "BuddyParallel"
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "buddy-parallel.log"
STATE_PATH = APP_DIR / "state.json"
DEFAULT_UPDATE_MANIFEST_URL = ""


@dataclass
class AppConfig:
    transport_mode: str = "auto"
    serial_port: str = ""
    serial_baud: int = 115200
    ble_device_name: str = ""
    hook_server_port: int = 43111
    api_server_port: int = 43112
    owner_name: str = ""
    device_name: str = "BuddyParallel"
    auto_start: bool = False
    update_manifest_url: str = ""


def validate_config(config: AppConfig) -> AppConfig:
    if config.transport_mode not in {"auto", "serial", "ble", "mock"}:
        raise ValueError("transport_mode must be auto, serial, ble, or mock")
    if config.serial_baud <= 0:
        raise ValueError("serial_baud must be positive")
    if config.hook_server_port <= 0 or config.api_server_port <= 0:
        raise ValueError("server ports must be positive")
    if config.update_manifest_url:
        parsed = urlparse(config.update_manifest_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("update_manifest_url must be a valid http or https URL")
    return config


class ConfigStore:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return validate_config(AppConfig(**{**asdict(AppConfig()), **data}))

    def save(self, config: AppConfig) -> None:
        config = validate_config(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
