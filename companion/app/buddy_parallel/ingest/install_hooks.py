from __future__ import annotations

import json
import sys
from pathlib import Path

from buddy_parallel.runtime.runtime_config import read_runtime_config
from buddy_parallel.services.hook_templates import CORE_HOOKS, build_command_entry, build_permission_entry

MARKER = "BuddyParallel hook_cli.py"


def settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def read_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_settings(path: Path, settings: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_event_hooks(settings: dict, command_template: str) -> None:
    hooks = settings.setdefault("hooks", {})
    for event in CORE_HOOKS:
        entries = hooks.setdefault(event, [])
        command = command_template.format(event=event)
        if not any(_entry_has_marker(entry) for entry in entries):
            entries.append(build_command_entry(command))


def ensure_permission_hook(settings: dict, url: str) -> None:
    hooks = settings.setdefault("hooks", {})
    entries = hooks.setdefault("PermissionRequest", [])
    if any(_permission_entry_matches(entry, url) for entry in entries):
        return
    entries.insert(0, build_permission_entry(url))


def _entry_has_marker(entry: dict) -> bool:
    hooks = entry.get("hooks") if isinstance(entry, dict) else None
    if not isinstance(hooks, list):
        return False
    return any(isinstance(hook, dict) and hook.get("type") == "command" and MARKER in str(hook.get("command", "")) for hook in hooks)


def _permission_entry_matches(entry: dict, url: str) -> bool:
    hooks = entry.get("hooks") if isinstance(entry, dict) else None
    if not isinstance(hooks, list):
        return False
    return any(isinstance(hook, dict) and hook.get("type") == "http" and hook.get("url") == url for hook in hooks)


def build_command_template() -> str:
    python_bin = Path(sys.executable).resolve().as_posix()
    hook_cli = (Path(__file__).resolve().parent / "hook_cli.py").as_posix()
    runtime = read_runtime_config()
    port = runtime.get("hook_server_port", 43111)
    base_url = f"http://127.0.0.1:{port}/state"
    return f'"{python_bin}" "{hook_cli}" "{base_url}" "{{event}}" # {MARKER}'


def build_permission_url() -> str:
    runtime = read_runtime_config()
    port = runtime.get("hook_server_port", 43111)
    return f"http://127.0.0.1:{port}/permission"


def main() -> None:
    path = settings_path()
    settings = read_settings(path)
    ensure_event_hooks(settings, build_command_template())
    ensure_permission_hook(settings, build_permission_url())
    write_settings(path, settings)
    print(f"BuddyParallel hooks installed at {path}")


if __name__ == "__main__":
    main()
