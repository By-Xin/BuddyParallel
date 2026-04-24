from __future__ import annotations

import subprocess
from pathlib import Path

from buddy_parallel.services.launching import LaunchSpec

class StartupManager:
    def __init__(self, startup_dir: Path | None = None, entry_name: str = "BuddyParallel Companion.vbs") -> None:
        self.startup_dir = startup_dir or (Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")
        self.entry_name = entry_name

    @property
    def entry_path(self) -> Path:
        return self.startup_dir / self.entry_name

    def is_enabled(self) -> bool:
        return self.entry_path.exists()

    def apply(self, enabled: bool, launch: LaunchSpec) -> None:
        entry = self.entry_path
        if not enabled:
            if entry.exists():
                entry.unlink()
            return

        working_dir = launch.working_dir.resolve()
        command = subprocess.list2cmdline([str(part) for part in launch.command])
        script = "\n".join(
            [
                'Set shell = CreateObject("WScript.Shell")',
                f'shell.CurrentDirectory = "{self._escape_vbs_string(str(working_dir))}"',
                f'shell.Run "{self._escape_vbs_string(command)}", 0, False',
            ]
        )

        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(script + "\n", encoding="utf-8")

    @staticmethod
    def _escape_vbs_string(value: str) -> str:
        return value.replace('"', '""')
