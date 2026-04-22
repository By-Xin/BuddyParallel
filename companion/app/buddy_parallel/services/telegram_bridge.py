from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import requests

from buddy_parallel.runtime.config import AppConfig
from buddy_parallel.runtime.state import StateStore


@dataclass
class BridgeStatus:
    telegram_ok: bool = False
    last_error: str = ""
    last_message_summary: str = "idle"


class TelegramClient:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"

    def get_updates(self, offset: int | None, timeout: int = 20) -> dict:
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        response = requests.get(f"{self.base_url}/getUpdates", params=params, timeout=timeout + 5)
        response.raise_for_status()
        return response.json()


class TelegramBridge:
    def __init__(
        self,
        config_supplier: Callable[[], AppConfig],
        message_sink: Callable[[str, list[str] | None, float, str, str, str, str], None],
        logger: logging.Logger,
        state_store: StateStore,
    ) -> None:
        self._config_supplier = config_supplier
        self._message_sink = message_sink
        self._logger = logger
        self._state_store = state_store
        self._runtime_state = self._state_store.load()
        self._status = BridgeStatus(
            last_error=self._runtime_state.last_telegram_error,
            last_message_summary=self._runtime_state.last_telegram_message_summary,
        )
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._reload = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._reload.clear()
        self._thread = threading.Thread(target=self._run, name="bp-telegram", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._reload.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def request_reload(self) -> None:
        self._runtime_state = self._state_store.load()
        self._reload.set()

    def status(self) -> BridgeStatus:
        with self._lock:
            return BridgeStatus(**self._status.__dict__)

    def _set_status(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self._status, key, value)

    def _sleep_or_reload(self, seconds: float) -> None:
        self._reload.wait(timeout=seconds)
        self._reload.clear()

    def _run(self) -> None:
        while not self._stop.is_set():
            config = self._config_supplier()
            if not config.bot_token or not config.allowed_chat_id:
                self._set_status(telegram_ok=False, last_error="configure bot token and allowed chat id")
                self._state_store.update(last_telegram_error="configure bot token and allowed chat id")
                self._sleep_or_reload(2.0)
                continue

            client = TelegramClient(config.bot_token)
            try:
                result = client.get_updates(
                    offset=self._runtime_state.telegram_offset,
                    timeout=max(1, config.poll_interval_seconds),
                )
                if not result.get("ok"):
                    message = "Telegram API returned ok=false"
                    self._set_status(telegram_ok=False, last_error=message)
                    self._state_store.update(last_telegram_error=message)
                    self._sleep_or_reload(2.0)
                    continue

                self._set_status(telegram_ok=True, last_error="")
                self._state_store.update(last_telegram_error="")
                for update in result.get("result", []):
                    self._runtime_state.telegram_offset = update["update_id"] + 1
                    self._state_store.update(telegram_offset=self._runtime_state.telegram_offset)
                    self._handle_update(config, update)
            except Exception as exc:
                if getattr(exc, "response", None) is not None and exc.response.status_code == 409:
                    message = "Telegram polling conflict: another getUpdates client is active"
                    self._logger.warning(message)
                    self._set_status(telegram_ok=False, last_error=message)
                    self._state_store.update(last_telegram_error=message)
                    self._sleep_or_reload(5.0)
                    continue
                self._logger.exception("Telegram polling failed")
                self._set_status(telegram_ok=False, last_error=str(exc))
                self._state_store.update(last_telegram_error=str(exc))
                self._sleep_or_reload(3.0)

    def _handle_update(self, config: AppConfig, update: dict) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        text = (message.get("text") or "").strip()
        chat_id = str(chat.get("id") or "")

        if not text:
            return
        if chat_id != config.allowed_chat_id:
            self._logger.info("Ignored Telegram message from unauthorized chat %s", chat_id)
            return

        title = str(chat.get("title") or chat.get("username") or chat.get("first_name") or "Telegram")
        stamp = datetime.fromtimestamp(int(message.get("date") or time.time())).strftime("%d %b %H:%M")
        base_notice_id = f"telegram-{update.get('update_id', message.get('message_id', int(time.time())))}"
        chunks = self._chunk_notice_text(text)
        total_chunks = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            summary = f"Message {index}/{total_chunks}: {chunk[:32]}" if total_chunks > 1 else f"Message: {chunk[:40]}"
            lines = [chunk[:90]]
            notice_id = f"{base_notice_id}-{index}"
            self._message_sink(summary, lines, 60.0, notice_id, "B.Y.", chunk, stamp)

        now = time.time()
        self._set_status(telegram_ok=True, last_error="", last_message_summary=text[:40])
        self._state_store.update(
            last_telegram_delivery_at=now,
            last_telegram_error="",
            last_telegram_message_summary=text[:40],
        )
        self._logger.info("Accepted Telegram message from %s", title)

    @staticmethod
    def _chunk_notice_text(text: str, max_chars: int = 48) -> list[str]:
        normalized = " ".join(text.split())
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
