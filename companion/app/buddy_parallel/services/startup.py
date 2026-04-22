from __future__ import annotations

from pathlib import Path


class StartupManager:
    def __init__(self, startup_dir: Path | None = None) -> None:
        self.startup_dir = startup_dir or (Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")

    def is_enabled(self) -> bool:
        return False

    def apply(self, enabled: bool, target: Path) -> None:
        _ = (enabled, target)
