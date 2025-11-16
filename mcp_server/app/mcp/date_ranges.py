from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Dict, Optional, Tuple

try:  # pragma: no cover - zoneinfo availability assumed in Python >=3.9
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - typing guard for unsupported runtimes
    ZoneInfo = None  # type: ignore
    ZoneInfoNotFoundError = Exception  # type: ignore


class DateRangeError(ValueError):
    """Raised when a configured timezone or range type is invalid."""


def resolve_timezone(name: Optional[str]) -> tzinfo:
    """Return a tzinfo instance for the provided IANA name or UTC by default."""

    if not name:
        return timezone.utc
    if ZoneInfo is None:
        raise DateRangeError("Timezone lookup is unavailable in this Python runtime")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:  # pragma: no cover - invalid config
        raise DateRangeError(f"Unknown timezone '{name}'") from exc


@dataclass(frozen=True)
class DateRange:
    """Helper storing the start/end moments for a calendar interval."""

    start: datetime
    end: datetime

    def iso_start(self) -> str:
        return self.start.isoformat()

    def iso_end(self) -> str:
        return self.end.isoformat()

    def date_start(self) -> str:
        return self.start.date().isoformat()

    def start_no_tz(self) -> str:
        return self.start.replace(tzinfo=None).isoformat()

    def end_no_tz(self) -> str:
        return self.end.replace(tzinfo=None).isoformat()


class DateRangeBuilder:
    """Constructs timezone-aware ranges used in warnings/hints."""

    VALID_KINDS = {"today", "yesterday", "last_week"}

    def __init__(self, tz: tzinfo) -> None:
        self._tz = tz

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _local_midnight(self, reference: datetime) -> datetime:
        local = reference.astimezone(self._tz)
        return local.replace(hour=0, minute=0, second=0, microsecond=0)

    def build_range(self, kind: str, reference: Optional[datetime] = None) -> DateRange:
        if kind not in self.VALID_KINDS:
            raise DateRangeError(f"Unsupported range type '{kind}'")
        now = reference or self._now()
        today_start = self._local_midnight(now)
        today_end = today_start + timedelta(hours=23, minutes=59, seconds=59)
        if kind == "today":
            return DateRange(start=today_start, end=today_end)
        if kind == "yesterday":
            start = today_start - timedelta(days=1)
            return DateRange(start=start, end=start + timedelta(hours=23, minutes=59, seconds=59))
        assert kind == "last_week"
        start = today_start - timedelta(days=7)
        return DateRange(start=start, end=today_end)

    @staticmethod
    def format_value(value: datetime, format_hint: str) -> str:
        if format_hint == "date":
            return value.date().isoformat()
        if format_hint == "datetime_no_tz":
            return value.replace(tzinfo=None).isoformat()
        return value.isoformat()

    def placeholders(self, kind: str, format_hint: str) -> Dict[str, str]:
        window = self.build_range(kind)
        placeholders: Dict[str, str] = {
            f"{kind}_start": window.iso_start(),
            f"{kind}_end": window.iso_end(),
            "range_start": self.format_value(window.start, format_hint),
            "range_end": self.format_value(window.end, format_hint),
        }
        if kind == "today":
            placeholders.update(
                {
                    "today_date": window.date_start(),
                    "today_start_no_tz": window.start_no_tz(),
                    "today_end_no_tz": window.end_no_tz(),
                }
            )
        return placeholders

    def week_placeholders(self) -> Dict[str, str]:
        window = self.build_range("last_week")
        return {
            "week_start": window.iso_start(),
            "week_end": window.iso_end(),
        }
