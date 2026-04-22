from __future__ import annotations

import json
import sys
from pathlib import Path

from buddy_parallel.runtime.runtime_config import read_runtime_config
from buddy_parallel.services.hook_templates import CORE_HOOKS, build_command_entry, build_permission_entry

MARKER = "BuddyParallel hook_cli.py"
LEGACY_COMMAND_MARKERS = (
    "HappyBuddy cc-hook.js",
    "Buddy_adj cc-hook.js",
    "Buddy_adj permission-hook.js",
    "clawd-hook.js",
    "Downloads/HappyBuddy",
    "Downloads/Buddy_adj",
    "Downloads/clawd-on-desk-main",
)
LEGACY_PERMISSION_URLS = {
    "http://127.0.0.1:23333/permission",
}


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
        entries = _remove_legacy_entries(hooks.setdefault(event, []))
        entries = _dedupe_buddyparallel_entries(entries)
        hooks[event] = entries
        command = command_template.format(event=event)
        if not any(_entry_has_marker(entry) for entry in entries):
            entries.append(build_command_entry(command))


def ensure_permission_hook(settings: dict, url: str) -> None:
    hooks = settings.setdefault("hooks", {})
    entries = _remove_legacy_entries(hooks.setdefault("PermissionRequest", []))
    entries = _dedupe_permission_entries(entries, url)
    hooks["PermissionRequest"] = entries
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


def _remove_legacy_entries(entries: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for entry in entries:
        if _is_legacy_entry(entry):
            continue
        cleaned.append(entry)
    return cleaned


def _dedupe_buddyparallel_entries(entries: list[dict]) -> list[dict]:
    kept: list[dict] = []
    seen = False
    for entry in entries:
        if _entry_has_marker(entry):
            if seen:
                continue
            seen = True
        kept.append(entry)
    return kept


def _dedupe_permission_entries(entries: list[dict], url: str) -> list[dict]:
    kept: list[dict] = []
    seen = False
    for entry in entries:
        if _permission_entry_matches(entry, url):
            if seen:
                continue
            seen = True
        kept.append(entry)
    return kept


def _is_legacy_entry(entry: dict) -> bool:
    hooks = entry.get("hooks") if isinstance(entry, dict) else None
    if not isinstance(hooks, list):
        return False
    for hook in hooks:
        if not isinstance(hook, dict):
            continue
        hook_type = str(hook.get("type") or "")
        if hook_type == "command":
            command = str(hook.get("command") or "")
            if any(marker in command for marker in LEGACY_COMMAND_MARKERS):
                return True
        if hook_type == "http":
            url = str(hook.get("url") or "")
            if url in LEGACY_PERMISSION_URLS:
                return True
    return False


def cleanup_hooks(settings: dict) -> None:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event in list(hooks):
        entries = hooks.get(event)
        if not isinstance(entries, list):
            continue
        cleaned = _remove_legacy_entries(entries)
        if event == "PermissionRequest":
            cleaned = _dedupe_permission_entries(cleaned, build_permission_url())
        else:
            cleaned = _dedupe_buddyparallel_entries(cleaned)
        if cleaned:
            hooks[event] = cleaned
            continue
        del hooks[event]


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
    cleanup_hooks(settings)
    ensure_event_hooks(settings, build_command_template())
    ensure_permission_hook(settings, build_permission_url())
    write_settings(path, settings)
    print(f"BuddyParallel hooks installed at {path}")


if __name__ == "__main__":
    main()
