from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable


NoticeSink = Callable[[str, list[str] | None, float, str, str, str, str], None]

DEFAULT_NOTICE_FROM = "B.Y."
DEFAULT_TTL_SECONDS = 60.0
MAX_ENTRY_LINES = 8
MAX_ENTRY_CHARS = 90
MAX_SUMMARY_CHARS = 40
# Firmware stores notice ids in `char[40]`, so the actual safe payload
# length is 39 plus the null terminator. Keep host-side ids within that
# limit so device notice_ack ids round-trip without truncation.
MAX_NOTICE_ID_CHARS = 39
MAX_NOTICE_FROM_CHARS = 16
MAX_NOTICE_BODY_CHARS = 90
MAX_NOTICE_STAMP_CHARS = 24
MAX_CHUNK_CHARS = 48


@dataclass(frozen=True)
class NoticeChunk:
    summary: str
    entries: list[str]
    ttl_seconds: float
    notice_id: str
    notice_from: str
    notice_body: str
    notice_stamp: str


def chunk_notice_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return ["(>_<) beep beep"]

    chunks: list[str] = []
    current = ""
    for word in normalized.split(" "):
        while len(word) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(word[:max_chars])
            word = word[max_chars:]
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks or ["(>_<) beep beep"]


def emit_notice_chunks(sink: NoticeSink, notices: list[NoticeChunk]) -> None:
    for notice in notices:
        sink(
            notice.summary,
            notice.entries,
            notice.ttl_seconds,
            notice.notice_id,
            notice.notice_from,
            notice.notice_body,
            notice.notice_stamp,
        )


def deliver_text_notice(
    sink: NoticeSink,
    text: str,
    *,
    base_notice_id: str,
    notice_from: str = DEFAULT_NOTICE_FROM,
    notice_stamp: str | None = None,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
) -> list[NoticeChunk]:
    notices = build_text_notice_chunks(
        text,
        base_notice_id=base_notice_id,
        notice_from=notice_from,
        notice_stamp=notice_stamp,
        ttl_seconds=ttl_seconds,
    )
    emit_notice_chunks(sink, notices)
    return notices


def build_text_notice_chunks(
    text: str,
    *,
    base_notice_id: str,
    notice_from: str = DEFAULT_NOTICE_FROM,
    notice_stamp: str | None = None,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
) -> list[NoticeChunk]:
    stamp = truncate_text(notice_stamp or format_notice_stamp(), MAX_NOTICE_STAMP_CHARS)
    sender = truncate_text(notice_from or DEFAULT_NOTICE_FROM, MAX_NOTICE_FROM_CHARS)
    base_id = truncate_text(base_notice_id or "notice", MAX_NOTICE_ID_CHARS)
    chunks = chunk_notice_text(text)
    total_chunks = len(chunks)
    notices: list[NoticeChunk] = []
    for index, chunk in enumerate(chunks, start=1):
        summary = (
            f"Message {index}/{total_chunks}: {chunk[:32]}"
            if total_chunks > 1
            else f"Message: {chunk[:MAX_SUMMARY_CHARS]}"
        )
        notices.append(
            NoticeChunk(
                summary=truncate_text(summary, MAX_SUMMARY_CHARS),
                entries=[truncate_text(chunk, MAX_ENTRY_CHARS)],
                ttl_seconds=coerce_ttl_seconds(ttl_seconds),
                notice_id=build_chunk_notice_id(base_id, index, total_chunks),
                notice_from=sender,
                notice_body=truncate_text(chunk, MAX_NOTICE_BODY_CHARS),
                notice_stamp=stamp,
            )
        )
    return notices


def build_mqtt_notice_chunks(
    payload: dict,
    *,
    fallback_notice_id: str,
    default_notice_from: str = DEFAULT_NOTICE_FROM,
    default_ttl_seconds: float = DEFAULT_TTL_SECONDS,
    received_at: datetime | None = None,
) -> list[NoticeChunk]:
    body_source = first_non_empty_string(
        payload.get("notice_body"),
        payload.get("body"),
        payload.get("text"),
        payload.get("message"),
    )
    entry_lines = sanitize_entries(payload.get("entries"))
    if not body_source and entry_lines:
        body_source = entry_lines[0]
    if not body_source:
        raise ValueError("notice payload missing body text")

    ttl_seconds = coerce_ttl_seconds(payload.get("ttl_seconds"), default=default_ttl_seconds)
    notice_from = truncate_text(
        first_non_empty_string(payload.get("notice_from"), payload.get("from"), default_notice_from),
        MAX_NOTICE_FROM_CHARS,
    )
    notice_stamp = truncate_text(
        first_non_empty_string(payload.get("notice_stamp")) or format_notice_stamp(received_at),
        MAX_NOTICE_STAMP_CHARS,
    )
    base_notice_id = truncate_text(
        first_non_empty_string(payload.get("notice_id")) or fallback_notice_id,
        MAX_NOTICE_ID_CHARS,
    )
    chunks = chunk_notice_text(body_source)
    total_chunks = len(chunks)
    summary_source = first_non_empty_string(payload.get("message"))
    notices: list[NoticeChunk] = []
    for index, chunk in enumerate(chunks, start=1):
        entries = entry_lines if total_chunks == 1 and entry_lines else [truncate_text(chunk, MAX_ENTRY_CHARS)]
        notices.append(
            NoticeChunk(
                summary=truncate_text(build_notice_summary(summary_source, chunk, index, total_chunks), MAX_SUMMARY_CHARS),
                entries=entries,
                ttl_seconds=ttl_seconds,
                notice_id=build_chunk_notice_id(base_notice_id, index, total_chunks),
                notice_from=notice_from,
                notice_body=truncate_text(chunk, MAX_NOTICE_BODY_CHARS),
                notice_stamp=notice_stamp,
            )
        )
    return notices


def build_notice_summary(summary_source: str | None, body_chunk: str, index: int, total: int) -> str:
    if summary_source:
        if total <= 1:
            return summary_source[:MAX_SUMMARY_CHARS]
        label = truncate_text(summary_source, 32)
        return f"{label} {index}/{total}"
    if total <= 1:
        return f"Message: {body_chunk[:MAX_SUMMARY_CHARS]}"
    return f"Message {index}/{total}: {body_chunk[:32]}"


def build_chunk_notice_id(base_notice_id: str, index: int, total: int) -> str:
    if total <= 1:
        return truncate_text(base_notice_id, MAX_NOTICE_ID_CHARS)
    suffix = f"-{index}"
    head = base_notice_id[: max(1, MAX_NOTICE_ID_CHARS - len(suffix))]
    return f"{head}{suffix}"


def sanitize_entries(value) -> list[str]:
    if not isinstance(value, list):
        return []
    entries: list[str] = []
    for item in value[:MAX_ENTRY_LINES]:
        text = " ".join(str(item or "").split())
        if text:
            entries.append(truncate_text(text, MAX_ENTRY_CHARS))
    return entries


def coerce_ttl_seconds(value, default: float = DEFAULT_TTL_SECONDS) -> float:
    try:
        ttl = float(value)
    except (TypeError, ValueError):
        ttl = float(default)
    return max(1.0, ttl)


def format_notice_stamp(moment: datetime | None = None) -> str:
    current = moment or datetime.now()
    return current.strftime("%d %b %H:%M")


def first_non_empty_string(*values) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def truncate_text(text: str, max_chars: int) -> str:
    return str(text or "")[:max_chars]
