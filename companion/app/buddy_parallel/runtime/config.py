from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

def _default_app_dir() -> Path:
    override = os.environ.get("BUDDY_PARALLEL_APP_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / "AppData" / "Roaming" / "BuddyParallel"


APP_DIR = _default_app_dir()
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "buddy-parallel.log"
STATE_PATH = APP_DIR / "state.json"
RUNTIME_PATH = APP_DIR / "runtime.json"
LOCK_PATH = APP_DIR / "buddy-parallel.lock"
DEFAULT_UPDATE_MANIFEST_URL = ""


@dataclass
class AppConfig:
    transport_mode: str = "auto"
    board_profile: str = "auto"
    serial_port: str = ""
    serial_baud: int = 115200
    ble_device_name: str = ""
    notice_transport: str = "off"
    notice_mqtt_url: str = ""
    notice_mqtt_topic: str = "devices/mcu1/notice"
    notice_mqtt_username: str = ""
    notice_mqtt_password: str = ""
    notice_mqtt_client_id: str = ""
    notice_mqtt_keepalive_seconds: int = 60
    weather_enabled: bool = False
    weather_location_query: str = ""
    weather_refresh_minutes: int = 30
    bot_token: str = ""
    allowed_chat_id: str = ""
    poll_interval_seconds: int = 3
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_allowed_chat_id: str = ""
    hook_server_port: int = 43111
    api_server_port: int = 43112
    owner_name: str = ""
    device_name: str = "BuddyParallel"
    festive_themes_enabled: bool = True
    birthday_mmdd: str = ""
    birthday_name: str = ""
    auto_start: bool = False
    update_manifest_url: str = ""


def parse_month_day(value: str) -> tuple[int | None, int | None]:
    text = str(value or "").strip()
    if not text:
        return None, None

    parts = text.split("-")
    if len(parts) == 2:
        month_text, day_text = parts
    elif len(parts) == 3:
        _, month_text, day_text = parts
    else:
        raise ValueError("birthday_mmdd must use MM-DD or YYYY-MM-DD")

    try:
        parsed = date(2000, int(month_text), int(day_text))
    except ValueError as exc:
        raise ValueError("birthday_mmdd must use MM-DD or YYYY-MM-DD") from exc
    return parsed.month, parsed.day


def validate_config(config: AppConfig) -> AppConfig:
    if config.transport_mode not in {"auto", "serial", "ble", "mock"}:
        raise ValueError("transport_mode must be auto, serial, ble, or mock")
    if config.board_profile not in {"auto", "m5stickc-plus", "m5stack-cores3"}:
        raise ValueError("board_profile must be auto, m5stickc-plus, or m5stack-cores3")
    if config.notice_transport not in {"off", "telegram", "mqtt", "feishu"}:
        raise ValueError("notice_transport must be off, telegram, mqtt, or feishu")
    if config.serial_baud <= 0:
        raise ValueError("serial_baud must be positive")
    if config.notice_mqtt_keepalive_seconds <= 0:
        raise ValueError("notice_mqtt_keepalive_seconds must be positive")
    if config.weather_refresh_minutes <= 0:
        raise ValueError("weather_refresh_minutes must be positive")
    if config.poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be positive")
    if config.hook_server_port <= 0 or config.api_server_port <= 0:
        raise ValueError("server ports must be positive")
    if config.notice_mqtt_url:
        parsed = urlparse(config.notice_mqtt_url)
        if parsed.scheme not in {"ws", "wss", "mqtt", "mqtts"} or not parsed.hostname:
            raise ValueError("notice_mqtt_url must be a valid ws, wss, mqtt, or mqtts URL")
    if config.update_manifest_url:
        parsed = urlparse(config.update_manifest_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("update_manifest_url must be a valid http or https URL")
    parse_month_day(config.birthday_mmdd)
    return config


class ConfigStore:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        return validate_config(AppConfig(**{**asdict(AppConfig()), **data}))

    def save(self, config: AppConfig) -> None:
        config = validate_config(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
