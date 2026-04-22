from __future__ import annotations

from dataclasses import dataclass

from buddy_parallel.runtime.config import AppConfig


@dataclass
class UpdateInfo:
    available: bool = False
    error: str = ""
    version: str = ""
    open_url: str = ""


class UpdateChecker:
    def check(self, config: AppConfig) -> UpdateInfo:
        if not config.update_manifest_url:
            return UpdateInfo(available=False, error="no update_manifest_url configured")
        return UpdateInfo(available=False)
