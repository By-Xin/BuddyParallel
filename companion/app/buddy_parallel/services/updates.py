from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests
from packaging.version import InvalidVersion, Version

from buddy_parallel import __version__
from buddy_parallel.runtime.config import AppConfig

MANIFEST_SCHEMA_VERSION = 1


class UpdateError(ValueError):
    pass


@dataclass
class UpdateInfo:
    available: bool
    error: str = ""
    version: str = ""
    open_url: str = ""
    notes: str = ""


def _read_string(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key)
    return str(value).strip() if value is not None else ""


def _read_url(obj: dict[str, Any], key: str) -> str:
    value = _read_string(obj, key)
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise UpdateError(f"manifest companion.{key} must be a valid http or https URL")
    return value


def _parse_manifest(manifest: Any) -> UpdateInfo:
    if not isinstance(manifest, dict):
        raise UpdateError("manifest root must be a JSON object")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise UpdateError(f"manifest schema_version must be {MANIFEST_SCHEMA_VERSION}")

    companion = manifest.get("companion")
    if not isinstance(companion, dict):
        raise UpdateError("manifest companion section is missing")

    version = _read_string(companion, "version")
    if not version:
        raise UpdateError("manifest companion.version is missing")

    download_url = _read_url(companion, "url")
    release_page_url = _read_url(companion, "release_page")
    if not download_url and not release_page_url:
        raise UpdateError("manifest companion.url or companion.release_page is required")

    return UpdateInfo(
        available=False,
        version=version,
        open_url=download_url or release_page_url,
        notes=_read_string(companion, "notes"),
    )


def _format_error(exc: Exception) -> str:
    if isinstance(exc, UpdateError):
        return str(exc)
    if isinstance(exc, requests.RequestException):
        return f"failed to fetch manifest: {exc}"
    return f"failed to parse manifest: {exc}"


class UpdateChecker:
    def check(self, config: AppConfig) -> UpdateInfo:
        manifest_url = config.update_manifest_url.strip()
        if not manifest_url:
            return UpdateInfo(False, error="no update_manifest_url configured")

        try:
            response = requests.get(manifest_url, timeout=10)
            response.raise_for_status()
            info = _parse_manifest(response.json())
            info.available = self._is_newer(info.version)
            return info
        except Exception as exc:
            return UpdateInfo(False, error=_format_error(exc))

    @staticmethod
    def build_available_message(info: UpdateInfo) -> str:
        notes = f" Notes: {info.notes}" if info.notes else ""
        return f"BuddyParallel {info.version} is available.{notes}".strip()

    @staticmethod
    def build_up_to_date_message() -> str:
        return f"You already have the latest BuddyParallel companion version ({__version__})."

    @staticmethod
    def build_error_message(error: str) -> str:
        return f"Update check failed: {error}"

    @staticmethod
    def _is_newer(latest: str) -> bool:
        if not latest:
            return False
        try:
            return Version(latest) > Version(__version__)
        except InvalidVersion:
            return latest != __version__
