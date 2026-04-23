from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

import requests

from buddy_parallel.runtime.config import AppConfig
from buddy_parallel.runtime.state import StateStore


@dataclass
class WeatherStatus:
    weather_ok: bool = False
    last_error: str = ""
    last_summary: str = "disabled"
    location_name: str = ""


class WeatherBridge:
    def __init__(
        self,
        config_supplier: Callable[[], AppConfig],
        weather_sink: Callable[[dict | None], None],
        logger: logging.Logger,
        state_store: StateStore,
    ) -> None:
        self._config_supplier = config_supplier
        self._weather_sink = weather_sink
        self._logger = logger
        self._state_store = state_store
        self._runtime_state = self._state_store.load()
        self._status = WeatherStatus(
            last_error=self._runtime_state.last_weather_error,
            last_summary=self._runtime_state.last_weather_summary,
            location_name=self._runtime_state.weather_location_name,
        )
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._reload = threading.Event()
        self._lock = threading.Lock()
        self._weather_applied = bool(isinstance(self._runtime_state.last_weather_payload, dict) and self._runtime_state.last_weather_payload)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._reload.clear()
        self._thread = threading.Thread(target=self._run, name="bp-weather", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._reload.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def request_reload(self) -> None:
        self._runtime_state = self._state_store.load()
        self._reload.set()

    def status(self) -> WeatherStatus:
        with self._lock:
            return WeatherStatus(**self._status.__dict__)

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
            if not config.weather_enabled:
                self._clear_applied_weather()
                self._set_status(weather_ok=False, last_error="", last_summary="disabled", location_name="")
                self._runtime_state = self._state_store.update(last_weather_error="", last_weather_summary="disabled")
                self._sleep_or_reload(2.0)
                continue

            query = " ".join(config.weather_location_query.split())
            if not query:
                self._clear_applied_weather()
                message = "set a weather location"
                self._set_status(weather_ok=False, last_error=message, last_summary="idle", location_name="")
                self._runtime_state = self._state_store.update(
                    weather_query="",
                    weather_location_name="",
                    weather_latitude=None,
                    weather_longitude=None,
                    weather_timezone="",
                    last_weather_error=message,
                    last_weather_summary="idle",
                    last_weather_payload=None,
                )
                self._sleep_or_reload(2.0)
                continue

            try:
                location = self._resolve_location(query)
                payload = self._fetch_weather(location)
                self._weather_sink(payload)
                self._weather_applied = True
                now = time.time()
                self._set_status(
                    weather_ok=True,
                    last_error="",
                    last_summary=payload["summary"],
                    location_name=payload["location"],
                )
                self._runtime_state = self._state_store.update(
                    weather_query=self._normalize_query(query),
                    weather_location_name=payload["location"],
                    weather_latitude=location["latitude"],
                    weather_longitude=location["longitude"],
                    weather_timezone=location["timezone"],
                    last_weather_error="",
                    last_weather_summary=payload["summary"],
                    last_weather_update_at=now,
                    last_weather_payload=payload,
                )
                self._logger.info("Weather updated for %s: %s", payload["location"], payload["summary"])
                self._sleep_or_reload(max(60.0, float(config.weather_refresh_minutes) * 60.0))
            except Exception as exc:
                self._logger.exception("Weather sync failed")
                self._set_status(
                    weather_ok=False,
                    last_error=str(exc),
                    last_summary=self._runtime_state.last_weather_summary or "idle",
                    location_name=self._runtime_state.weather_location_name,
                )
                self._runtime_state = self._state_store.update(last_weather_error=str(exc))
                self._sleep_or_reload(10.0)

    def _clear_applied_weather(self) -> None:
        if not self._weather_applied:
            return
        self._weather_sink(None)
        self._weather_applied = False

    def _resolve_location(self, query: str) -> dict:
        normalized_query = self._normalize_query(query)
        state = self._state_store.load()
        self._runtime_state = state
        if (
            state.weather_query == normalized_query
            and state.weather_latitude is not None
            and state.weather_longitude is not None
            and state.weather_timezone
            and state.weather_location_name
        ):
            return {
                "name": state.weather_location_name,
                "latitude": float(state.weather_latitude),
                "longitude": float(state.weather_longitude),
                "timezone": state.weather_timezone,
            }

        response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": query, "count": 1, "language": "en", "format": "json"},
            headers={"User-Agent": "BuddyParallel/1.0"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        if not results:
            self._clear_applied_weather()
            self._runtime_state = self._state_store.update(
                weather_query=normalized_query,
                weather_location_name="",
                weather_latitude=None,
                weather_longitude=None,
                weather_timezone="",
                last_weather_payload=None,
            )
            raise ValueError(f"no weather location found for '{query}'")

        top = self._pick_location_result(query, results)
        return {
            "name": self._format_location_name(top),
            "latitude": float(top["latitude"]),
            "longitude": float(top["longitude"]),
            "timezone": str(top["timezone"]),
        }

    def _fetch_weather(self, location: dict) -> dict:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "current": "temperature_2m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": 1,
                "timezone": location["timezone"],
                "temperature_unit": "celsius",
            },
            headers={"User-Agent": "BuddyParallel/1.0"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        current = data.get("current") or {}
        daily = data.get("daily") or {}
        temp_c = self._round_int(current.get("temperature_2m"))
        high_c = self._first_int(daily.get("temperature_2m_max"), fallback=temp_c)
        low_c = self._first_int(daily.get("temperature_2m_min"), fallback=temp_c)
        rain_pct = self._first_int(daily.get("precipitation_probability_max"), fallback=0)
        code = int(current.get("weather_code") or 0)
        condition = self._condition_label(code)
        board_summary = self._build_board_summary(temp_c, condition)
        tray_summary = f"{temp_c}C {condition} | H{high_c} L{low_c} | {rain_pct}%"
        return {
            "location": location["name"][:40],
            "summary": tray_summary[:64],
            "board_summary": board_summary[:23],
            "condition": condition,
            "weather_code": code,
            "current_temp_c": temp_c,
            "high_c": high_c,
            "low_c": low_c,
            "precip_probability_pct": rain_pct,
            "timezone": location["timezone"],
            "updated_at": time.time(),
        }

    @staticmethod
    def _normalize_query(query: str) -> str:
        return " ".join(query.lower().split())

    @staticmethod
    def _format_location_name(result: dict) -> str:
        parts = [str(result.get("name") or "").strip()]
        admin1 = str(result.get("admin1") or "").strip()
        country = str(result.get("country") or result.get("country_code") or "").strip()
        if admin1 and admin1.lower() != parts[0].lower():
            parts.append(admin1)
        if country and all(country.lower() != part.lower() for part in parts):
            parts.append(country)
        return ", ".join(part for part in parts if part)[:40]

    @classmethod
    def _pick_location_result(cls, query: str, results: list[dict]) -> dict:
        normalized = cls._normalize_query(query)

        def score(item: dict) -> tuple[int, int]:
            name = cls._normalize_query(str(item.get("name") or ""))
            population = int(item.get("population") or 0)
            if name == normalized:
                return (3, population)
            if name.startswith(normalized):
                return (2, population)
            if normalized in name:
                return (1, population)
            return (0, population)

        return max(results, key=score)

    @staticmethod
    def _round_int(value, fallback: int = 0) -> int:
        try:
            if value is None:
                return fallback
            return int(round(float(value)))
        except (TypeError, ValueError):
            return fallback

    @classmethod
    def _first_int(cls, values, fallback: int = 0) -> int:
        if not values:
            return fallback
        return cls._round_int(values[0], fallback=fallback)

    @staticmethod
    def _condition_label(code: int) -> str:
        if code == 0:
            return "Clear"
        if code in {1, 2, 3}:
            return "Cloud"
        if code in {45, 48}:
            return "Fog"
        if code in {51, 53, 55}:
            return "Driz"
        if code in {56, 57}:
            return "FDriz"
        if code in {61, 63, 65}:
            return "Rain"
        if code in {66, 67}:
            return "FRain"
        if code in {71, 73, 75}:
            return "Snow"
        if code == 77:
            return "Grain"
        if code in {80, 81, 82}:
            return "Shwr"
        if code in {85, 86}:
            return "SShwr"
        if code in {95, 96, 99}:
            return "Storm"
        return "Weather"

    @staticmethod
    def _build_board_summary(temp_c: int, condition: str) -> str:
        return f"{temp_c}C {condition}"
