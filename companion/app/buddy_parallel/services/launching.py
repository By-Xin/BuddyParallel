from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LaunchSpec:
    command: list[str]
    working_dir: Path


def companion_root() -> Path:
    return Path(__file__).resolve().parents[3]


def repo_root() -> Path:
    return companion_root().parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _python_launcher(*, windowed: bool) -> Path:
    executable = Path(sys.executable).resolve()
    lower = executable.name.lower()
    if windowed and lower == "python.exe":
        candidate = executable.with_name("pythonw.exe")
        if candidate.exists():
            return candidate
    if not windowed and lower == "pythonw.exe":
        candidate = executable.with_name("python.exe")
        if candidate.exists():
            return candidate
    return executable


def build_companion_command(*args: str, windowed: bool = False) -> LaunchSpec:
    if is_frozen():
        return LaunchSpec([str(Path(sys.executable).resolve()), *args], Path(sys.executable).resolve().parent)

    script = companion_root() / "scripts" / "run_companion.py"
    launcher = _python_launcher(windowed=windowed)
    return LaunchSpec([str(launcher), str(script), *args], repo_root())
