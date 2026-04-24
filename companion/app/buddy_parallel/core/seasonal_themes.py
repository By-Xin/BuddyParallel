from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from buddy_parallel.runtime.config import AppConfig, parse_month_day


@dataclass(frozen=True)
class SeasonalTheme:
    key: str
    title: str
    subtitle: str
    detail: str = ""


def resolve_seasonal_theme(config: AppConfig, today: date | None = None) -> SeasonalTheme | None:
    if not config.festive_themes_enabled:
        return None

    current = today or date.today()
    return (
        _birthday_theme(config, current)
        or _christmas_theme(current)
        or _new_year_theme(current)
    )


def _birthday_theme(config: AppConfig, today: date) -> SeasonalTheme | None:
    month, day = parse_month_day(config.birthday_mmdd)
    if month is None or day is None or (today.month, today.day) != (month, day):
        return None

    name = str(config.birthday_name or config.owner_name or "").strip()
    detail = f"{name} Day" if name else "Cake Mode"
    return SeasonalTheme(key="birthday", title="Happy", subtitle="Birthday", detail=detail[:18])


def _christmas_theme(today: date) -> SeasonalTheme | None:
    if today.month != 12 or today.day not in {24, 25, 26}:
        return None
    return SeasonalTheme(
        key="christmas",
        title="Merry",
        subtitle="XMAS",
        detail="Holiday Mode",
    )


def _new_year_theme(today: date) -> SeasonalTheme | None:
    if not ((today.month == 12 and today.day == 31) or (today.month == 1 and today.day in {1, 2})):
        return None
    return SeasonalTheme(
        key="new-year",
        title="Hello",
        subtitle=str(today.year),
        detail="New Year",
    )
