from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from buddy_parallel.runtime.config import APP_DIR, LOG_PATH


def configure_logging() -> logging.Logger:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("buddy_parallel")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = _build_file_handler()
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    active_path = getattr(file_handler, "baseFilename", str(LOG_PATH))
    if active_path != str(LOG_PATH):
        logger.warning("Primary log file unavailable; using fallback log at %s", active_path)

    return logger


def _build_file_handler() -> RotatingFileHandler:
    candidates = [
        LOG_PATH,
        APP_DIR / "buddy-parallel-fallback.log",
    ]
    last_error: OSError | None = None
    for path in candidates:
        try:
            return RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        except OSError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error
