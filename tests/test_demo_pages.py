"""Validate demo templates against declared plugin variables."""

import json
import re
from pathlib import Path
from unittest.mock import Mock

import pytest


MANIFEST_PATH = Path(__file__).resolve().parents[1] / "manifest.json"


def _manifest():
    return json.loads(MANIFEST_PATH.read_text())


def _cases():
    return [(name, demo["template"]) for name, demo in _manifest()["demo"].items()]


@pytest.mark.parametrize("device_type,template", _cases())
def test_demo_variables_are_declared(device_type, template):
    manifest = _manifest()
    plugin_id = manifest["id"]
    variables = manifest["variables"]
    simple = {f"{plugin_id}.{name}" for name in variables.get("simple", {})}
    arrays = variables.get("arrays", {})
    valid = set(simple)
    for array_name, spec in arrays.items():
        for index in range(10):
            for field in spec.get("item_fields", []):
                valid.add(f"{plugin_id}.{array_name}.{index}.{field}")

    references = {
        match.group(1).strip()
        for line in template
        for match in re.finditer(r"\{\{([^}]+)\}\}", line)
    }
    assert references <= valid, f"{device_type} uses undeclared variables: {references - valid}"


@pytest.mark.parametrize("device_type,demo", _manifest()["demo"].items())
def test_demo_renders_at_exact_board_dimensions(device_type, demo):
    from src.templates.engine import TemplateEngine

    departures = [
        {"flight": "AS123", "destination": "LAX", "compact_time": "1930"},
        {"flight": "DL456", "destination": "SFO", "compact_time": "2015"},
        {"flight": "UA789", "destination": "ORD", "compact_time": "2045"},
    ]
    context = {
        "airport_departures": {
            "airport": "SEA",
            "departure_count": 3,
            "departures": departures,
            "line1": "SEA DEPARTURES",
            "line2": "AS123 LAX 1930",
            "line3": "DL456 SFO 2015",
        }
    }
    engine = TemplateEngine.__new__(TemplateEngine)
    engine._config_manager = Mock()
    engine._config_manager.get_color_rules.return_value = []
    engine._plugin_registry = None
    rendered = engine.render_lines(
        demo["template"],
        context=context,
        line_metadata=demo.get("line_metadata"),
        device_type=device_type,
    )
    rows, columns = (3, 15) if device_type == "note" else (6, 22)
    lines = rendered.splitlines()
    assert len(lines) == rows
    assert all(engine._count_tiles(line) == columns for line in lines)
    assert "{{" not in rendered
