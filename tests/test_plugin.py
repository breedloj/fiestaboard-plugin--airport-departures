from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_plugin_module():
    module_name = "airport_departures_external"
    sys.modules.pop(module_name, None)
    sys.modules.pop(f"{module_name}.provider", None)
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
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


def test_airlabs_arrival_query_and_normalization():
    provider = load_provider_module()
    payload = {
        "response": [
            airlabs_arrival(
                "AS2248",
                "SFO",
                "2026-07-13 21:44",
                estimated="2026-07-13 21:50",
                status="active",
            )
        ]
    }
    with patch.object(provider.requests, "get", return_value=response(payload)) as request:
        rows = provider.AirLabsProvider("secret").fetch_arrivals("PAE", 10)

    params = request.call_args.kwargs["params"]
    assert params["arr_iata"] == "PAE"
    assert "dep_iata" not in params
    assert rows[0]["board_type"] == "arrivals"
    assert rows[0]["origin"] == "SFO"
    assert rows[0]["destination"] == "PAE"
    assert rows[0]["counterpart_airport"] == "SFO"
    assert rows[0]["compact_time"] == "2150"
    assert rows[0]["terminal"] == "A"
    assert rows[0]["gate"] == "A2"
    assert rows[0]["baggage"] == "5"
    assert rows[0]["status_code"] == "ENR"
    assert rows[0]["status_label"] == "EN ROUTE"


def test_existing_provider_subclasses_remain_valid():
    provider = load_provider_module()

    class ExistingProvider(provider.DepartureProvider):
        def fetch_departures(self, airport, limit):
            return []

    adapter = ExistingProvider()
    assert adapter.fetch_departures("SEA", 2) == []
    with pytest.raises(provider.ProviderError, match="does not support arrival"):
        adapter.fetch_arrivals("SEA", 2)


def test_airlabs_excludes_non_airline_movements():
    provider = load_provider_module()
    airline = airlabs_departure("AS123", "LAX", "2026-07-13 19:30")
    no_airline = {**airline, "flight_iata": "N123AB", "airline_iata": ""}
    no_flight = {**airline, "flight_iata": ""}
    payload = {"response": [no_airline, no_flight, airline]}
    with patch.object(provider.requests, "get", return_value=response(payload)):
        rows = provider.AirLabsProvider("secret").fetch_departures("PAE", 10)
    assert [row["flight"] for row in rows] == ["AS123"]


def test_airlabs_derives_numbers_when_optional_fields_are_missing():
    provider = load_provider_module()
    row = airlabs_departure("AS2248", "SFO", "2026-07-13 21:44")
    row.pop("flight_number")
    row.update(cs_flight_iata="QX2248")
    normalized_row = provider._normalize_airlabs(row)
    assert normalized_row["flight_number"] == "2248"
    assert normalized_row["codeshare_number"] == "2248"


def test_primary_marketing_flight_wins_over_partner_and_operator_aliases():
    module = load_plugin_module()
    marketing = normalized("AS2248", "SFO", "2026-07-13T21:44:00-07:00", "ON", "ON TIME")
    marketing.update(
        flight_number="2248",
        codeshare_flight="QX2248",
        codeshare_number="2248",
    )
    operator = normalized("QX2248", "SFO", "2026-07-13T21:44:00-07:00", "ON", "ON TIME")
    operator.update(flight_number="2248", codeshare_flight="", codeshare_number="")
    partner = normalized("FJ5869", "SFO", "2026-07-13T21:44:00-07:00", "ON", "ON TIME")
    partner.update(
        flight_number="5869",
        codeshare_flight="AS2248",
        codeshare_number="2248",
    )
    assert module.Plugin(manifest())._deduplicate([partner, operator, marketing]) == [marketing]


def test_distinct_simultaneous_departures_are_not_combined():
    module = load_plugin_module()
    first = normalized("AS123", "SFO", "2026-07-13T21:44:00-07:00", "ON", "ON TIME")
    first.update(flight_number="123", codeshare_flight="", codeshare_number="")
    second = normalized("UA456", "SFO", "2026-07-13T21:44:00-07:00", "ON", "ON TIME")
    second.update(flight_number="456", codeshare_flight="", codeshare_number="")
    assert module.Plugin(manifest())._deduplicate([first, second]) == [first, second]


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


def test_airlabs_rejects_invalid_json_and_error_payloads():
    provider = load_provider_module()
    invalid_json = response({})
    invalid_json.json.side_effect = ValueError("not JSON")
    with patch.object(provider.requests, "get", return_value=invalid_json):
        with pytest.raises(provider.ProviderError, match="invalid JSON"):
            provider.AirLabsProvider("secret").fetch_departures("SEA", 10)

    api_error = response({"error": {"message": "request limit reached"}})
    with patch.object(provider.requests, "get", return_value=api_error):
        with pytest.raises(provider.ProviderError, match="request limit reached"):
            provider.AirLabsProvider("secret").fetch_departures("SEA", 10)

    unexpected = response({"response": "not-a-list"})
    with patch.object(provider.requests, "get", return_value=unexpected):
        with pytest.raises(provider.ProviderError, match="unexpected response"):
            provider.AirLabsProvider("secret").fetch_departures("SEA", 10)


@pytest.mark.parametrize(
    ("status", "delayed", "code", "label", "color"),
    [
        ("cancelled", 0, "CNCL", "CANCELLED", "{63}"),
        ("departed", 0, "DEPT", "DEPARTED", "{67}"),
        ("boarding", 0, "BRD", "BOARDING", "{66}"),
        ("delayed", 25, "DLY", "DELAY 25M", "{64}"),
    ],
)
def test_provider_status_mapping(status, delayed, code, label, color):
    provider = load_provider_module()
    assert provider._status(status, delayed) == (code, label)
    assert provider._status_color(status, delayed) == color


def test_departure_status_colors_retain_legacy_defaults():
    provider = load_provider_module()
    assert provider._status_color("diverted", 0) == "{66}"
    assert provider._status_color("incident", 0) == "{66}"


@pytest.mark.parametrize(
    ("status", "code", "label", "color"),
    [
        ("landed", "ARR", "ARRIVED", "{67}"),
        ("active", "ENR", "EN ROUTE", "{67}"),
        ("diverted", "DIV", "DIVERTED", "{65}"),
        ("incident", "INFO", "SEE AGENT", "{63}"),
    ],
)
def test_arrival_status_mapping(status, code, label, color):
    provider = load_provider_module()
    assert provider._status(status, 0, "arrivals") == (code, label)
    assert provider._status_color(status, 0, "arrivals") == color


def test_delayed_departure_keeps_updated_time_on_note():
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
    assert result.data["line3"] == "DL456 SFO 1930"
    assert result.data["minutes_until_departure"] == 30
    assert result.data["departures"][1]["minutes_until_departure"] == 60
    assert result.data["board_type"] == "departures"
    assert result.data["arrival_count"] == 0
    assert result.data["arrivals"] == []
    assert result.data["minutes_until_arrival"] == -1
    assert result.data["has_delays"]
    assert all(len(line) <= 15 for line in result.formatted_lines[:3])
    provider.fetch_departures.assert_called_once_with("SEA", limit=50)
    provider.fetch_arrivals.assert_not_called()


def test_arrivals_use_origins_and_arrival_variables_on_note():
    module = load_plugin_module()
    plugin = module.Plugin(manifest())
    plugin.config = {
        "api_key": "secret",
        "board_type": "arrivals",
        "airport_iata": "PAE",
        "timezone": "America/Los_Angeles",
        "max_departures": 2,
        "recent_departure_minutes": 0,
    }
    rows = [
        normalized_arrival("AS2248", "SFO", "2026-07-13T21:44:00-07:00"),
        normalized_arrival("AS2055", "LAX", "2026-07-13T22:30:00-07:00"),
    ]
    provider = Mock()
    provider.fetch_arrivals.return_value = rows
    with plugin._bound_board(SimpleNamespace(device_type="note")):
        with patch.object(plugin, "_provider", return_value=provider), patch.object(
            plugin,
            "_now",
            return_value=datetime(2026, 7, 13, 20, 44, tzinfo=ZoneInfo("America/Los_Angeles")),
        ):
            result = plugin.fetch_data()

    assert result.available
    assert result.data["board_type"] == "arrivals"
    assert result.data["line1"] == "PAE ARRIVALS"
    assert result.data["line2"] == "AS2248 SFO 2144"
    assert result.data["line3"] == "AS2055 LAX 2230"
    assert result.data["origin"] == "SFO"
    assert result.data["arrival_count"] == 2
    assert result.data["departure_count"] == 0
    assert result.data["departures"] == []
    assert result.data["minutes_until_departure"] == -1
    assert result.data["minutes_until_arrival"] == 60
    assert result.data["arrivals"][1]["minutes_until_arrival"] == 106
    provider.fetch_arrivals.assert_called_once_with("PAE", limit=50)
    provider.fetch_departures.assert_not_called()


def test_empty_arrival_board_is_available_and_direction_aware():
    module = load_plugin_module()
    plugin = module.Plugin(manifest())
    plugin.config = {
        "api_key": "secret",
        "board_type": "arrivals",
        "airport_iata": "PAE",
        "timezone": "UTC",
    }
    provider = Mock()
    provider.fetch_arrivals.return_value = []
    with patch.object(plugin, "_provider", return_value=provider):
        result = plugin.fetch_data()

    assert result.available
    assert result.data["line1"] == "PAE ARRIVALS"
    assert result.data["line2"] == "NO ARRIVALS"
    assert result.data["arrival_count"] == 0
    assert result.data["arrivals"] == []


def test_single_departure_leaves_second_slot_empty():
    module = load_plugin_module()
    plugin = module.Plugin(manifest())
    plugin.config = {"api_key": "secret", "airport_iata": "SEA", "timezone": "UTC"}
    item = normalized("AS123", "LAX", "2026-07-13T20:00:00+00:00", "ON", "ON TIME")
    provider = Mock()
    provider.fetch_departures.return_value = [item]
    with patch.object(plugin, "_provider", return_value=provider), patch.object(
        plugin, "_now", return_value=datetime(2026, 7, 13, 19, tzinfo=ZoneInfo("UTC"))
    ):
        result = plugin.fetch_data()
    assert result.data["line3"] == ""


def test_boarding_row_with_six_character_flight_fits_note():
    module = load_plugin_module()
    item = normalized("AB1234", "LAX", "2026-07-13T20:00:00+00:00", "BRD", "BOARDING")
    assert module._compact_line(item, 15) == "AB1234 LAX 1930"
    assert len(module._compact_line(item, 15)) <= 15


def test_validation_requires_key_and_iata():
    module = load_plugin_module()
    plugin = module.Plugin(manifest())
    errors = plugin.validate_config({"airport_iata": "SE", "timezone": "UTC"})
    assert len(errors) == 2


def test_validation_rejects_unknown_board_type():
    module = load_plugin_module()
    plugin = module.Plugin(manifest())
    errors = plugin.validate_config(
        {
            "api_key": "secret",
            "airport_iata": "SEA",
            "timezone": "UTC",
            "board_type": "both",
        }
    )
    assert errors == ["Board type must be departures or arrivals"]


def test_manifest_allows_environment_api_key():
    assert "api_key" not in manifest()["settings_schema"]["required"]


def test_manifest_defaults_existing_installations_to_departures():
    plugin_manifest = manifest()
    assert plugin_manifest["version"] == "1.3.0"
    assert plugin_manifest["settings_schema"]["properties"]["board_type"]["default"] == "departures"
    assert "departures" in plugin_manifest["variables"]["arrays"]
    assert "arrivals" in plugin_manifest["variables"]["arrays"]


def test_null_board_type_is_treated_as_legacy_departures():
    module = load_plugin_module()
    plugin = module.Plugin(manifest())
    plugin.config = {"board_type": None}
    assert plugin._board_type() == "departures"


def test_missing_departure_time_uses_unavailable_sentinel():
    module = load_plugin_module()
    assert module._minutes_until_departure({}, datetime(2026, 7, 13, tzinfo=ZoneInfo("UTC"))) == -1
    assert module._minutes_until_arrival({}, datetime(2026, 7, 13, tzinfo=ZoneInfo("UTC"))) == -1


def test_cancelled_departure_is_not_relevant():
    module = load_plugin_module()
    item = normalized("AS123", "LAX", "2026-07-13T20:00:00+00:00", "CNCL", "CANCELLED")
    item["status"] = "cancelled"
    now = datetime(2026, 7, 13, 19, tzinfo=ZoneInfo("UTC"))
    assert not module.Plugin(manifest())._is_relevant(item, now, 0)


def airlabs_departure(flight, destination, dep_time, delayed=0):
    return {
        "flight_iata": flight,
        "flight_number": flight[2:],
        "airline_iata": flight[:2],
        "dep_iata": "SEA",
        "dep_time": dep_time,
        "arr_iata": destination,
        "status": "scheduled",
        "dep_delayed": delayed,
    }


def airlabs_arrival(flight, origin, arr_time, estimated="", status="scheduled", delayed=0):
    return {
        "flight_iata": flight,
        "flight_number": flight[2:],
        "airline_iata": flight[:2],
        "dep_iata": origin,
        "arr_iata": "PAE",
        "arr_time": arr_time,
        "arr_estimated": estimated,
        "arr_terminal": "A",
        "arr_gate": "A2",
        "arr_baggage": "5",
        "status": status,
        "arr_delayed": delayed,
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


def normalized_arrival(flight, origin, sort_time):
    return {
        **normalized(flight, "PAE", sort_time, "ON", "ON TIME"),
        "origin": origin,
        "baggage": "5",
        "compact_time": datetime.fromisoformat(sort_time).strftime("%H%M"),
    }
