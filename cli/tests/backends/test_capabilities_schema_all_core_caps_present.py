from __future__ import annotations

import json
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parents[2] / "src" / "robot_md" / "schemas" / "capabilities.json"

# Mirrors backends/registry.py CORE_CAPABILITY_PREFIXES (introduced in Task 2).
_CORE_PREFIXES = ("arm.", "nav.", "perceive.", "gripper.", "safety.")


def test_every_core_prefix_has_at_least_one_capability_defined() -> None:
    schema = json.loads(_SCHEMA_PATH.read_text())
    defined = set(schema["definitions"].keys())
    for prefix in _CORE_PREFIXES:
        assert any(name.startswith(prefix) for name in defined), (
            f"capabilities.json has no capability for core prefix {prefix!r}"
        )
