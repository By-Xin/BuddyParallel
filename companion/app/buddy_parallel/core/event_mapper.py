from __future__ import annotations

from typing import Any

EVENT_TO_STATE = {
    "SessionStart": "idle",
    "SessionEnd": "sleeping",
    "UserPromptSubmit": "thinking",
    "PreToolUse": "working",
    "PostToolUse": "working",
    "PostToolUseFailure": "error",
    "Stop": "idle",
    "StopFailure": "error",
    "SubagentStart": "working",
    "SubagentStop": "working",
    "Notification": "notification",
    "Elicitation": "notification",
    "PreCompact": "working",
    "PostCompact": "attention",
    "WorktreeCreate": "working",
}


def normalize_event(payload: dict[str, Any]) -> dict[str, Any]:
    event = str(payload.get("event") or payload.get("hook_event_name") or "")
    state = str(payload.get("state") or EVENT_TO_STATE.get(event) or "idle")
    session_id = str(payload.get("session_id") or "default")
    session_title = payload.get("session_title") or "Claude Code"
    message = _default_message(event=event, state=state, session_title=str(session_title))
    normalized = {
        "source": str(payload.get("source") or "hook"),
        "event": event,
        "state": state,
        "session_id": session_id,
        "session_title": session_title,
        "cwd": str(payload.get("cwd") or ""),
        "message": str(payload.get("message") or payload.get("msg") or message),
        "running": bool(payload.get("running", state in {"thinking", "working", "busy"})),
        "waiting": bool(payload.get("waiting", state == "attention")),
        "completed": bool(payload.get("completed", event == "Notification")),
    }
    if isinstance(payload.get("entries"), list):
        normalized["entries"] = [str(item) for item in payload["entries"][:8]]
    if isinstance(payload.get("tokens"), int):
        normalized["tokens"] = payload["tokens"]
    if isinstance(payload.get("tokens_today"), int):
        normalized["tokens_today"] = payload["tokens_today"]
    return normalized


def _default_message(event: str, state: str, session_title: str) -> str:
    if state == "thinking":
        return f"{session_title}: thinking"
    if state == "working":
        return f"{session_title}: working"
    if state == "attention":
        return f"{session_title}: approval needed"
    if state == "notification":
        return f"{session_title}: notification"
    if state == "error":
        return f"{session_title}: tool failed"
    if event == "SessionEnd":
        return f"{session_title}: ended"
    return f"{session_title}: idle"
