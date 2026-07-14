"""Real airport departure boards for FiestaBoard."""

from __future__ import annotations

import logging
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
    """Display real scheduled departures for one airport."""

    @property
    def plugin_id(self) -> str:
        return "airport_departures"

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
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
        airport = str(self.config.get("airport_iata", "")).strip().upper()
        api_key = str(self.config.get("api_key") or os.getenv("AIRLABS_API_KEY") or "").strip()
        validation_errors = self.validate_config({**self.config, "api_key": api_key})
        if validation_errors:
            return PluginResult(available=False, error="; ".join(validation_errors))

        provider = self._provider(api_key)
        try:
            departures = provider.fetch_departures(airport, limit=50)
        except ProviderError as exc:
            logger.warning("Airport departures fetch failed: %s", exc)
            return PluginResult(available=False, error=str(exc))

        tz = self._timezone()
        now = self._now(tz)
        recent_minutes = max(0, min(180, int(self.config.get("recent_departure_minutes", 45))))
        max_departures = max(1, min(10, int(self.config.get("max_departures", 5))))
        departures = [
            item for item in departures
            if self._is_relevant(item, now, recent_minutes)
        ]
        departures = self._deduplicate(departures)
        departures.sort(key=lambda item: item.get("sort_time", ""))
        departures = departures[:max_departures]

        if not departures:
            data = self._empty_data(airport)
            return PluginResult(available=True, data=data, formatted_lines=self._format_display(data))

        primary = departures[0]
        data = {
            **primary,
            "airport": airport,
            "departure_count": len(departures),
            "has_delays": any(item.get("is_delayed") for item in departures),
            "departures": departures,
        }
        data.update(self._display_fields(airport, departures))
        return PluginResult(available=True, data=data, formatted_lines=self._format_display(data))

    def _provider(self, api_key: str) -> DepartureProvider:
        return AirLabsProvider(api_key=api_key)

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
        seen: set[tuple[str, str, str]] = set()
        unique: list[dict[str, Any]] = []
        for item in items:
            key = (
                str(item.get("flight", "")),
                str(item.get("destination", "")),
                str(item.get("scheduled_time", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    @staticmethod
    def _display_fields(airport: str, departures: list[dict[str, Any]]) -> dict[str, str]:
        lines = [_compact_line(item, 15) for item in departures[:2]]
        if len(lines) == 1:
            lines.append(_detail_line(departures[0], 15))
        while len(lines) < 2:
            lines.append("")
        return {
            "header": _fit(f"{airport} DEPARTURES", 15),
            "line1": _fit(f"{airport} DEPARTURES", 15),
            "line2": lines[0],
            "line3": lines[1],
            "formatted": _compact_line(departures[0], 22),
        }

    def _format_display(self, data: dict[str, Any]) -> list[str]:
        device_type = getattr(self.board, "device_type", "flagship") if self.board else "flagship"
        if device_type == "note":
            return [data.get("line1", "DEPARTURES"), data.get("line2", "NO DEPARTURES"), data.get("line3", "")]
        lines = [str(data.get("airport", "AIRPORT") + " DEPARTURES").center(22)]
        for departure in data.get("departures", [])[:4]:
            lines.append(_compact_line(departure, 22))
        while len(lines) < 6:
            lines.append("")
        return lines[:6]

    @staticmethod
    def _empty_data(airport: str) -> dict[str, Any]:
        return {
            "airport": airport,
            "flight": "",
            "destination": "",
            "departure_count": 0,
            "has_delays": False,
            "departures": [],
            "header": _fit(f"{airport} DEPARTURES", 15),
            "line1": _fit(f"{airport} DEPARTURES", 15),
            "line2": "NO DEPARTURES",
            "line3": "",
            "formatted": "NO DEPARTURES",
        }


def _compact_line(item: dict[str, Any], width: int) -> str:
    flight = _fit(item.get("flight") or "FLIGHT", 6)
    destination = _fit(item.get("destination") or "---", 3)
    if item.get("status_code") in {"DLY", "CNCL", "BOARD", "DEPT"}:
        suffix = str(item.get("status_code"))
    else:
        suffix = str(item.get("compact_time") or item.get("display_time") or "----")
    return _fit(f"{flight} {destination} {suffix}", width)


def _detail_line(item: dict[str, Any], width: int) -> str:
    parts: list[str] = []
    if item.get("gate"):
        parts.append(f"GATE {item['gate']}")
    parts.append(str(item.get("status_label") or "ON TIME"))
    return _fit(" ".join(parts), width)


def _fit(value: Any, width: int) -> str:
    return str(value or "").strip()[:width]


Plugin = AirportDeparturesPlugin
