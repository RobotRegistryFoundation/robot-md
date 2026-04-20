from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "src/robot_md/schemas/v1/robot.schema.json").read_text()
)


def _m(solver):
    return {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "bob"},
        "physics": {"type": "arm", "dof": 6, "solver": solver},
        "drivers": [{"id": "arm", "protocol": "feetech"}],
        "capabilities": ["status.report"],
        "safety": {"estop": {"software": True, "response_ms": 100}},
    }


def test_ik_provider_null_allowed():
    jsonschema.validate(_m({"ik_provider": None}), SCHEMA)


def test_ik_provider_string_allowed():
    jsonschema.validate(_m({"ik_provider": "inhouse-so-arm101"}), SCHEMA)


def test_ik_frame_null_allowed():
    jsonschema.validate(_m({"ik_frame": None}), SCHEMA)


def test_ik_frame_string_allowed():
    jsonschema.validate(_m({"ik_frame": "ready"}), SCHEMA)


def test_ik_provider_numeric_rejected():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_m({"ik_provider": 42}), SCHEMA)


def test_ik_frame_list_rejected():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_m({"ik_frame": ["ready", "stowed"]}), SCHEMA)


def test_solver_block_still_optional_and_permissive():
    """physics.solver without ik fields still valid; other solver keys still allowed."""
    jsonschema.validate(_m({"convention": "DH", "encoder": {"steps_per_rev": 4096}}), SCHEMA)
