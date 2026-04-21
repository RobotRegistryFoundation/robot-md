from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "src/robot_md/schemas/v1/robot.schema.json").read_text()
)


def _m(physics_extra=None):
    physics = {"type": "arm", "dof": 6}
    if physics_extra:
        physics.update(physics_extra)
    return {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "bob"},
        "physics": physics,
        "drivers": [{"id": "arm", "protocol": "feetech"}],
        "capabilities": ["status.report"],
        "safety": {"estop": {"software": True, "response_ms": 100}},
    }


def test_workspace_optional():
    jsonschema.validate(_m(), SCHEMA)


def test_workspace_accepts_bounds_mm():
    jsonschema.validate(
        _m(
            {
                "workspace": {
                    "from_pose": "ready",
                    "bounds_mm": {"x": [-200, 200], "y": [50, 300], "z": [0, 150]},
                    "note": "Tabletop manipulation envelope.",
                }
            }
        ),
        SCHEMA,
    )


def test_workspace_accepts_only_one_axis():
    """Not all three axes required — can describe partial bounds."""
    jsonschema.validate(_m({"workspace": {"bounds_mm": {"x": [-200, 200]}}}), SCHEMA)


def test_workspace_rejects_single_element_axis():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_m({"workspace": {"bounds_mm": {"x": [1]}}}), SCHEMA)


def test_workspace_rejects_three_element_axis():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_m({"workspace": {"bounds_mm": {"x": [1, 2, 3]}}}), SCHEMA)
