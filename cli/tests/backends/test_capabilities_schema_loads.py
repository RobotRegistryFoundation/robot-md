from __future__ import annotations

import json
from pathlib import Path


def test_capabilities_schema_parses_as_json() -> None:
    path = Path(__file__).parents[2] / "src" / "robot_md" / "schemas" / "capabilities.json"
    data = json.loads(path.read_text())
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "definitions" in data
