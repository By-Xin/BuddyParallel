from __future__ import annotations

CORE_HOOKS = [
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Stop",
    "StopFailure",
    "SubagentStart",
    "SubagentStop",
    "Notification",
    "Elicitation",
    "PreCompact",
    "PostCompact",
    "WorktreeCreate",
]


def build_command_entry(command: str) -> dict:
    return {"matcher": "", "hooks": [{"type": "command", "command": command}]}


def build_permission_entry(url: str) -> dict:
    return {"matcher": "", "hooks": [{"type": "http", "url": url, "timeout": 600}]}
