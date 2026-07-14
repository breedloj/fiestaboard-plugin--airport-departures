"""Flight schedule provider adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import requests

AIRLABS_SCHEDULES_URL = "https://airlabs.co/api/v9/schedules"
REQUEST_TIMEOUT = 20


class ProviderError(RuntimeError):
    """A departure provider could not return usable data."""


class DepartureProvider(ABC):
    @abstractmethod
    def fetch_departures(self, airport: str, limit: int) -> list[dict[str, Any]]:
        """Return normalized departure dictionaries."""


class AirLabsProvider(DepartureProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch_departures(self, airport: str, limit: int = 50) -> list[dict[str, Any]]:
        params = {
            "api_key": self.api_key,
            "dep_iata": airport,
            "limit": max(1, min(50, limit)),
            "_fields": (
                "flight_iata,flight_number,airline_iata,dep_iata,dep_time,dep_estimated,"
                "dep_actual,dep_terminal,dep_gate,arr_iata,status,dep_delayed"
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
        return [parsed for row in rows if isinstance(row, dict) if (parsed := _normalize_airlabs(row))]


def _normalize_airlabs(row: dict[str, Any]) -> dict[str, Any] | None:
    airline = str(row.get("airline_iata") or "").strip().upper()
    flight = str(row.get("flight_iata") or "").strip().upper()
    destination = str(row.get("arr_iata") or "").strip().upper()
    # Published IATA identifiers distinguish scheduled airline service from
    # private, positioning, and other general-aviation movements.
    if not airline or not flight or not destination:
        return None

    scheduled = str(row.get("dep_time") or "").strip()
    estimated = str(row.get("dep_estimated") or "").strip()
    actual = str(row.get("dep_actual") or "").strip()
    effective = actual or estimated or scheduled
    status = str(row.get("status") or "scheduled").strip().lower()
    try:
        delayed = max(0, int(float(row.get("dep_delayed") or 0)))
    except (TypeError, ValueError):
        delayed = 0
    status_code, status_label = _status(status, delayed)
    return {
        "flight": flight,
        "airline": airline,
        "destination": destination,
        "scheduled_time": scheduled,
        "estimated_time": estimated,
        "actual_time": actual,
        "sort_time": effective,
        "display_time": _display_time(effective),
        "compact_time": _compact_time(effective),
        "terminal": str(row.get("dep_terminal") or ""),
        "gate": str(row.get("dep_gate") or ""),
        "status": status,
        "status_code": status_code,
        "status_label": status_label,
        "delay_minutes": delayed,
        "is_delayed": delayed > 0 or status == "delayed",
        "status_color": _status_color(status, delayed),
    }


def _status(status: str, delayed: int) -> tuple[str, str]:
    if status in {"cancelled", "canceled"}:
        return "CNCL", "CANCELLED"
    if status in {"active", "departed", "en-route", "en_route", "landed"}:
        return "DEPT", "DEPARTED"
    if status in {"boarding"}:
        return "BRD", "BOARDING"
    if status == "delayed" or delayed > 0:
        return "DLY", f"DELAY {delayed}M" if delayed else "DELAYED"
    return "ON", "ON TIME"


def _status_color(status: str, delayed: int) -> str:
    if status in {"cancelled", "canceled"}:
        return "{63}"
    if status == "delayed" or delayed > 0:
        return "{64}"
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
