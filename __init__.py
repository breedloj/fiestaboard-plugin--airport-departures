"""Real airport departure and arrival boards for FiestaBoard."""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.plugins.base import PluginBase, PluginResult

try:
    from .provider import AirLabsProvider, DepartureProvider, ProviderError
except ImportError:  # Direct loading of a standalone external plugin.
    from provider import AirLabsProvider, DepartureProvider, ProviderError

logger = logging.getLogger(__name__)


class AirportDeparturesPlugin(PluginBase):
    """Display real scheduled departures or arrivals for one airport."""

    @property
    def plugin_id(self) -> str:
        return "airport_departures"

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        board_type = str(config.get("board_type") or "departures").strip().lower()
        if board_type not in {"departures", "arrivals"}:
            errors.append("Board type must be departures or arrivals")
        airport = str(config.get("airport_iata", "")).strip().upper()
        if len(airport) != 3 or not airport.isalpha():
            errors.append("Airport must be a three-letter IATA code, such as SEA")
        if not config.get("api_key") and not os.getenv("AIRLABS_API_KEY"):
            errors.append("AirLabs API key is required")
        try:
            ZoneInfo(str(config.get("timezone", "UTC")))
        except ZoneInfoNotFoundError:
            errors.append("Timezone must be a valid IANA name, such as America/Los_Angeles")
        return errors

    def fetch_data(self) -> PluginResult:
        board_type = self._board_type()
        airport = str(self.config.get("airport_iata", "")).strip().upper()
        api_key = str(self.config.get("api_key") or os.getenv("AIRLABS_API_KEY") or "").strip()
        validation_errors = self.validate_config({**self.config, "api_key": api_key})
        if validation_errors:
            return PluginResult(available=False, error="; ".join(validation_errors))

        provider = self._provider(api_key)
        try:
            if board_type == "arrivals":
                movements = provider.fetch_arrivals(airport, limit=50)
            else:
                movements = provider.fetch_departures(airport, limit=50)
        except ProviderError as exc:
            logger.warning("Airport %s fetch failed: %s", board_type, exc)
            return PluginResult(available=False, error=str(exc))

        tz = self._timezone()
        now = self._now(tz)
        recent_minutes = max(0, min(180, int(self.config.get("recent_departure_minutes", 45))))
        max_flights = max(1, min(10, int(self.config.get("max_departures", 5))))
        movements = [
            item for item in movements
            if self._is_relevant(item, now, recent_minutes)
        ]
        for item in movements:
            item.setdefault("board_type", board_type)
            item.setdefault(
                "counterpart_airport",
                item.get("origin") if board_type == "arrivals" else item.get("destination", ""),
            )
        movements = self._deduplicate(movements)
        movements.sort(key=lambda item: item.get("sort_time", ""))
        movements = movements[:max_flights]
        for item in movements:
            minutes_until = _minutes_until(item, now)
            item["minutes_until_departure"] = minutes_until if board_type == "departures" else -1
            item["minutes_until_arrival"] = minutes_until if board_type == "arrivals" else -1

        if not movements:
            data = self._empty_data(airport, board_type)
            return PluginResult(available=True, data=data, formatted_lines=self._format_display(data))

        primary = movements[0]
        is_arrivals = board_type == "arrivals"
        data = {
            **primary,
            "airport": airport,
            "board_type": board_type,
            "departure_count": 0 if is_arrivals else len(movements),
            "arrival_count": len(movements) if is_arrivals else 0,
            "has_delays": any(item.get("is_delayed") for item in movements),
            "minutes_until_departure": -1 if is_arrivals else primary["minutes_until_departure"],
            "minutes_until_arrival": primary["minutes_until_arrival"] if is_arrivals else -1,
            "departures": [] if is_arrivals else movements,
            "arrivals": movements if is_arrivals else [],
        }
        data.update(self._display_fields(airport, movements, board_type))
        return PluginResult(available=True, data=data, formatted_lines=self._format_display(data))

    def _provider(self, api_key: str) -> DepartureProvider:
        return AirLabsProvider(api_key=api_key)

    def _board_type(self) -> str:
        value = str(self.config.get("board_type") or "departures").strip().lower()
        return "arrivals" if value == "arrivals" else "departures"

    def _timezone(self) -> ZoneInfo:
        try:
            return ZoneInfo(str(self.config.get("timezone", "UTC")))
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    @staticmethod
    def _now(tz: ZoneInfo) -> datetime:
        return datetime.now(tz)

    @staticmethod
    def _is_relevant(item: dict[str, Any], now: datetime, recent_minutes: int) -> bool:
        if str(item.get("status", "")).lower() in {"cancelled", "canceled"}:
            return False
        raw = str(item.get("sort_time", ""))
        if not raw:
            return True
        try:
            departure = datetime.fromisoformat(raw)
        except ValueError:
            return True
        if departure.tzinfo is None:
            departure = departure.replace(tzinfo=now.tzinfo)
        return departure >= now - timedelta(minutes=recent_minutes)

    @staticmethod
    def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        positions: dict[tuple[str, str, str], int] = {}
        unique: list[dict[str, Any]] = []
        for item in items:
            service_number = str(
                item.get("codeshare_number")
                or item.get("flight_number")
                or item.get("codeshare_flight")
                or item.get("flight")
            )
            key = (
                service_number,
                str(item.get("counterpart_airport") or item.get("destination", "")),
                str(item.get("scheduled_time", "")),
            )
            if key in positions:
                existing_index = positions[key]
                existing = unique[existing_index]
                if _listing_score(item) > _listing_score(existing):
                    unique[existing_index] = item
                continue
            positions[key] = len(unique)
            unique.append(item)
        return unique

    @staticmethod
    def _display_fields(
        airport: str,
        movements: list[dict[str, Any]],
        board_type: str = "departures",
    ) -> dict[str, str]:
        label = board_type.upper()
        lines = [_compact_line(item, 15) for item in movements[:2]]
        while len(lines) < 2:
            lines.append("")
        return {
            "header": _fit(f"{airport} {label}", 15),
            "line1": _fit(f"{airport} {label}", 15),
            "line2": lines[0],
            "line3": lines[1],
            "formatted": _compact_line(movements[0], 22),
        }

    def _format_display(self, data: dict[str, Any]) -> list[str]:
        board_type = str(data.get("board_type", "departures"))
        label = board_type.upper()
        movements = data.get("arrivals" if board_type == "arrivals" else "departures", [])
        device_type = getattr(self.board, "device_type", "flagship") if self.board else "flagship"
        if device_type == "note":
            return [data.get("line1", label), data.get("line2", f"NO {label}"), data.get("line3", "")]
        lines = [str(data.get("airport", "AIRPORT") + f" {label}").center(22)]
        for movement in movements[:4]:
            lines.append(_compact_line(movement, 22))
        while len(lines) < 6:
            lines.append("")
        return lines[:6]

    @staticmethod
    def _empty_data(airport: str, board_type: str = "departures") -> dict[str, Any]:
        label = board_type.upper()
        return {
            "airport": airport,
            "board_type": board_type,
            "flight": "",
            "origin": "",
            "destination": "",
            "departure_count": 0,
            "arrival_count": 0,
            "has_delays": False,
            "minutes_until_departure": -1,
            "minutes_until_arrival": -1,
            "departures": [],
            "arrivals": [],
            "header": _fit(f"{airport} {label}", 15),
            "line1": _fit(f"{airport} {label}", 15),
            "line2": f"NO {label}",
            "line3": "",
            "formatted": f"NO {label}",
        }


def _compact_line(item: dict[str, Any], width: int) -> str:
    flight = _fit(item.get("flight") or "FLIGHT", 6)
    counterpart = _fit(
        item.get("counterpart_airport")
        or (item.get("origin") if item.get("board_type") == "arrivals" else item.get("destination"))
        or "---",
        3,
    )
    suffix = str(item.get("compact_time") or item.get("display_time") or "----")
    return _fit(f"{flight} {counterpart} {suffix}", width)


def _listing_score(item: dict[str, Any]) -> int:
    """Prefer the primary marketing flight over operator and partner aliases."""
    flight_number = str(item.get("flight_number") or "")
    codeshare_number = str(item.get("codeshare_number") or "")
    if item.get("codeshare_flight") and flight_number == codeshare_number:
        return 3
    if not item.get("codeshare_flight"):
        return 2
    return 1


def _minutes_until_departure(item: dict[str, Any], now: datetime) -> int:
    return _minutes_until(item, now)


def _minutes_until_arrival(item: dict[str, Any], now: datetime) -> int:
    return _minutes_until(item, now)


def _minutes_until(item: dict[str, Any], now: datetime) -> int:
    raw = str(item.get("sort_time") or "")
    if not raw:
        return -1
    try:
        departure = datetime.fromisoformat(raw)
    except ValueError:
        return -1
    if departure.tzinfo is None:
        departure = departure.replace(tzinfo=now.tzinfo)
    return max(-1, math.ceil((departure - now).total_seconds() / 60))


def _fit(value: Any, width: int) -> str:
    return str(value or "").strip()[:width]


Plugin = AirportDeparturesPlugin
