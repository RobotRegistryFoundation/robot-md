from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from robot_md.backends.lerobot import LerobotBackend

_SCHEMA_PATH = Path(__file__).parents[2] / "src" / "robot_md" / "schemas" / "capabilities.json"


_MINIMAL_ARGS = {
    "arm.pick": {"target": "red_lego"},
    "arm.place": {"destination": "drop_zone"},
    "arm.home": {},
    "perceive.rgb": {},
    "perceive.depth": {},
    "gripper.open": {},
    "gripper.close": {},
}


def test_minimal_valid_args_per_core_capability_pass_validation() -> None:
    schema = json.loads(_SCHEMA_PATH.read_text())
    defs = schema["definitions"]
    backend_caps = LerobotBackend().capabilities()
    validated: list[str] = []
    for cap in backend_caps:
        if cap not in defs:
            continue  # vendor capability — not in capabilities.json
        assert cap in _MINIMAL_ARGS, f"missing minimal-args fixture for core capability {cap!r}"
        jsonschema.validate(_MINIMAL_ARGS[cap], defs[cap])
        validated.append(cap)
    # Sanity: we expect every core capability the backend declares to have been
    # validated. If this number drifts low, something is silently being skipped.
    expected_core_caps = backend_caps - frozenset({"lerobot.teleop"})
    assert frozenset(validated) == expected_core_caps, (
        f"core caps validated {sorted(validated)!r} differs from declared "
        f"core caps {sorted(expected_core_caps)!r}"
    )
