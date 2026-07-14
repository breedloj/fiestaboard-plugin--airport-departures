from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]


def load_plugin_module():
    spec = importlib.util.spec_from_file_location(
        "airport_departures_external",
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_provider_module():
    spec = importlib.util.spec_from_file_location("airport_provider", ROOT / "provider.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def manifest():
    return json.loads((ROOT / "manifest.json").read_text())


def response(payload):
    result = Mock()
    result.json.return_value = payload
    result.raise_for_status.return_value = None
    return result


def test_airlabs_normalization():
    provider = load_provider_module()
    payload = {"response": [airlabs_departure("AS123", "LAX", "2026-07-13 19:30", delayed=0)]}
    with patch.object(provider.requests, "get", return_value=response(payload)):
        rows = provider.AirLabsProvider("secret").fetch_departures("SEA", 10)
    assert rows[0]["flight"] == "AS123"
    assert rows[0]["destination"] == "LAX"
    assert rows[0]["status_code"] == "ON"
    assert rows[0]["display_time"] == "7:30 PM"
    assert rows[0]["compact_time"] == "1930"


def test_fiestaboard_loader_accepts_standalone_repo(tmp_path):
    from src.plugins.loader import PluginLoader

    (tmp_path / "airport_departures").symlink_to(ROOT, target_is_directory=True)
    loader = PluginLoader(plugins_dir=tmp_path, external_dirs=[])
    plugin = loader.load_plugin("airport_departures")
    assert plugin is not None, loader._load_errors.get("airport_departures")


def test_airlabs_http_error_does_not_expose_api_key():
    provider = load_provider_module()
    http_error = provider.requests.HTTPError(
        "429 for https://airlabs.co/api/v9/schedules?api_key=very-secret",
        response=Mock(status_code=429),
    )
    with patch.object(provider.requests, "get", side_effect=http_error):
        try:
            provider.AirLabsProvider("very-secret").fetch_departures("SEA", 10)
        except provider.ProviderError as exc:
            assert str(exc) == "AirLabs request failed (HTTP 429)"
            assert "very-secret" not in str(exc)
        else:
            raise AssertionError("Expected ProviderError")


def test_delayed_departure_uses_compact_status():
    module = load_plugin_module()
    plugin = module.Plugin(manifest())
    plugin.config = {
        "api_key": "secret",
        "airport_iata": "SEA",
        "timezone": "America/Los_Angeles",
        "max_departures": 5,
        "recent_departure_minutes": 45,
    }
    rows = [
        normalized("AS123", "LAX", "2026-07-13T19:30:00-07:00", "ON", "ON TIME"),
        normalized("DL456", "SFO", "2026-07-13T20:00:00-07:00", "DLY", "DELAY 25M", True),
    ]
    provider = Mock()
    provider.fetch_departures.return_value = rows
    with plugin._bound_board(SimpleNamespace(device_type="note")):
        with patch.object(plugin, "_provider", return_value=provider), patch.object(
            plugin,
            "_now",
            return_value=datetime(2026, 7, 13, 19, tzinfo=ZoneInfo("America/Los_Angeles")),
        ):
            result = plugin.fetch_data()
    assert result.available
    assert result.data["line1"] == "SEA DEPARTURES"
    assert result.data["line3"] == "DL456 SFO DLY"
    assert result.data["has_delays"]
    assert all(len(line) <= 15 for line in result.formatted_lines[:3])


def test_single_departure_shows_gate_detail():
    module = load_plugin_module()
    plugin = module.Plugin(manifest())
    plugin.config = {"api_key": "secret", "airport_iata": "SEA", "timezone": "UTC"}
    item = normalized("AS123", "LAX", "2026-07-13T20:00:00+00:00", "ON", "ON TIME")
    item["gate"] = "N12"
    provider = Mock()
    provider.fetch_departures.return_value = [item]
    with patch.object(plugin, "_provider", return_value=provider), patch.object(
        plugin, "_now", return_value=datetime(2026, 7, 13, 19, tzinfo=ZoneInfo("UTC"))
    ):
        result = plugin.fetch_data()
    assert result.data["line3"] == "N12 ON TIME"


def test_boarding_row_with_six_character_flight_fits_note():
    module = load_plugin_module()
    item = normalized("AB1234", "LAX", "2026-07-13T20:00:00+00:00", "BRD", "BOARDING")
    assert module._compact_line(item, 15) == "AB1234 LAX BRD"
    assert len(module._compact_line(item, 15)) <= 15


def test_validation_requires_key_and_iata():
    module = load_plugin_module()
    plugin = module.Plugin(manifest())
    errors = plugin.validate_config({"airport_iata": "SE", "timezone": "UTC"})
    assert len(errors) == 2


def test_manifest_allows_environment_api_key():
    assert "api_key" not in manifest()["settings_schema"]["required"]


def airlabs_departure(flight, destination, dep_time, delayed=0):
    return {
        "flight_iata": flight,
        "airline_iata": flight[:2],
        "dep_iata": "SEA",
        "dep_time": dep_time,
        "arr_iata": destination,
        "status": "scheduled",
        "delayed": delayed,
    }


def normalized(flight, destination, sort_time, status_code, status_label, delayed=False):
    return {
        "flight": flight,
        "airline": flight[:2],
        "destination": destination,
        "scheduled_time": sort_time,
        "estimated_time": "",
        "actual_time": "",
        "sort_time": sort_time,
        "display_time": "7:30 PM",
        "compact_time": "1930",
        "terminal": "N",
        "gate": "",
        "status": "delayed" if delayed else "scheduled",
        "status_code": status_code,
        "status_label": status_label,
        "delay_minutes": 25 if delayed else 0,
        "is_delayed": delayed,
        "status_color": "{64}" if delayed else "{66}",
    }
