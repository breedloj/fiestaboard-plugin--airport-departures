"""Flight schedule provider adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import requests

AIRLABS_SCHEDULES_URL = "https://airlabs.co/api/v9/schedules"
REQUEST_TIMEOUT = 20


class ProviderError(RuntimeError):
    """A flight schedule provider could not return usable data."""


class DepartureProvider(ABC):
    @abstractmethod
    def fetch_departures(self, airport: str, limit: int) -> list[dict[str, Any]]:
        """Return normalized departure dictionaries."""

    def fetch_arrivals(self, airport: str, limit: int) -> list[dict[str, Any]]:
        """Return normalized arrival dictionaries when the provider supports them."""
        raise ProviderError("This provider does not support arrival boards")


class AirLabsProvider(DepartureProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch_departures(self, airport: str, limit: int = 50) -> list[dict[str, Any]]:
        return self._fetch_schedule(airport, limit, "departures")

    def fetch_arrivals(self, airport: str, limit: int = 50) -> list[dict[str, Any]]:
        return self._fetch_schedule(airport, limit, "arrivals")

    def _fetch_schedule(
        self,
        airport: str,
        limit: int,
        board_type: str,
    ) -> list[dict[str, Any]]:
        airport_filter = "arr_iata" if board_type == "arrivals" else "dep_iata"
        params = {
            "api_key": self.api_key,
            airport_filter: airport,
            "limit": max(1, min(50, limit)),
            "_fields": (
                "flight_iata,flight_number,airline_iata,dep_iata,dep_time,dep_estimated,"
                "dep_actual,dep_terminal,dep_gate,dep_delayed,arr_iata,arr_time,"
                "arr_estimated,arr_actual,arr_terminal,arr_gate,arr_baggage,arr_delayed,"
                "status,"
                "cs_airline_iata,cs_flight_iata,cs_flight_number"
            ),
        }
        try:
            response = requests.get(AIRLABS_SCHEDULES_URL, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = f" (HTTP {status})" if status else ""
            raise ProviderError(f"AirLabs request failed{detail}") from exc
        except ValueError as exc:
            raise ProviderError("AirLabs returned invalid JSON") from exc

        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise ProviderError(f"AirLabs: {message or 'unknown API error'}")

        rows = payload.get("response", []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ProviderError("AirLabs returned an unexpected response")
        return [
            parsed
            for row in rows
            if isinstance(row, dict)
            if (parsed := _normalize_airlabs(row, board_type))
        ]


def _normalize_airlabs(
    row: dict[str, Any],
    board_type: str = "departures",
) -> dict[str, Any] | None:
    airline = str(row.get("airline_iata") or "").strip().upper()
    flight = str(row.get("flight_iata") or "").strip().upper()
    codeshare_flight = str(row.get("cs_flight_iata") or "").strip().upper()
    flight_number = str(row.get("flight_number") or flight[2:]).strip().upper()
    codeshare_number = str(
        row.get("cs_flight_number") or codeshare_flight[2:]
    ).strip().upper()
    origin = str(row.get("dep_iata") or "").strip().upper()
    destination = str(row.get("arr_iata") or "").strip().upper()
    counterpart = origin if board_type == "arrivals" else destination
    # Published IATA identifiers distinguish scheduled airline service from
    # private, positioning, and other general-aviation movements.
    if not airline or not flight or not counterpart:
        return None

    prefix = "arr" if board_type == "arrivals" else "dep"
    scheduled = str(row.get(f"{prefix}_time") or "").strip()
    estimated = str(row.get(f"{prefix}_estimated") or "").strip()
    actual = str(row.get(f"{prefix}_actual") or "").strip()
    effective = actual or estimated or scheduled
    status = str(row.get("status") or "scheduled").strip().lower()
    try:
        delay_value = row.get(f"{prefix}_delayed")
        if delay_value is None:
            delay_value = row.get("delayed")
        delayed = max(0, int(float(delay_value or 0)))
    except (TypeError, ValueError):
        delayed = 0
    status_code, status_label = _status(status, delayed, board_type)
    return {
        "board_type": board_type,
        "flight": flight,
        "flight_number": flight_number,
        "airline": airline,
        "codeshare_flight": codeshare_flight,
        "codeshare_number": codeshare_number,
        "origin": origin,
        "destination": destination,
        "counterpart_airport": counterpart,
        "scheduled_time": scheduled,
        "estimated_time": estimated,
        "actual_time": actual,
        "sort_time": effective,
        "display_time": _display_time(effective),
        "compact_time": _compact_time(effective),
        "terminal": str(row.get(f"{prefix}_terminal") or ""),
        "gate": str(row.get(f"{prefix}_gate") or ""),
        "baggage": str(row.get("arr_baggage") or "") if board_type == "arrivals" else "",
        "status": status,
        "status_code": status_code,
        "status_label": status_label,
        "delay_minutes": delayed,
        "is_delayed": delayed > 0 or status == "delayed",
        "status_color": _status_color(status, delayed, board_type),
    }


def _status(
    status: str,
    delayed: int,
    board_type: str = "departures",
) -> tuple[str, str]:
    if status in {"cancelled", "canceled"}:
        return "CNCL", "CANCELLED"
    if board_type == "arrivals":
        if status == "landed":
            return "ARR", "ARRIVED"
        if status in {"active", "departed", "en-route", "en_route"}:
            return "ENR", "EN ROUTE"
        if status == "diverted":
            return "DIV", "DIVERTED"
        if status == "incident":
            return "INFO", "SEE AGENT"
    if status in {"active", "departed", "en-route", "en_route", "landed"}:
        return "DEPT", "DEPARTED"
    if status in {"boarding"}:
        return "BRD", "BOARDING"
    if status == "delayed" or delayed > 0:
        return "DLY", f"DELAY {delayed}M" if delayed else "DELAYED"
    return "ON", "ON TIME"


def _status_color(
    status: str,
    delayed: int,
    board_type: str = "departures",
) -> str:
    if status in {"cancelled", "canceled"}:
        return "{63}"
    if board_type == "arrivals" and status == "incident":
        return "{63}"
    if status == "delayed" or delayed > 0:
        return "{64}"
    if board_type == "arrivals" and status == "diverted":
        return "{65}"
    if status in {"active", "departed", "en-route", "en_route", "landed"}:
        return "{67}"
    return "{66}"


def _display_time(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return value[-5:]


def _compact_time(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%H%M")
    except ValueError:
        return value[-5:].replace(":", "")
