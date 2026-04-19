"""Schema v1 accepts optional physics.poses with named joint dicts."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "src/robot_md/schemas/v1/robot.schema.json").read_text()
)


def _min_manifest(extra_physics: dict | None = None) -> dict:
    physics = {"type": "arm", "dof": 6}
    if extra_physics:
        physics.update(extra_physics)
    return {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "bob"},
        "physics": physics,
        "drivers": [{"id": "arm", "protocol": "feetech"}],
        "capabilities": ["status.report"],
        "safety": {"estop": {"software": True, "response_ms": 100}},
    }


def test_poses_block_is_optional():
    jsonschema.validate(_min_manifest(), SCHEMA)


def test_poses_block_accepts_named_poses():
    m = _min_manifest({
        "poses": {
            "ready": {
                "description": "arm extended forward",
                "joints": {"shoulder_pan": 2048, "shoulder_lift": 1600},
                "source": "taught",
                "taught_at": "2026-04-19",
            }
        }
    })
    jsonschema.validate(m, SCHEMA)


def test_poses_rejects_unknown_source_enum():
    m = _min_manifest({"poses": {"ready": {"joints": {"a": 1}, "source": "guessed"}}})
    try:
        jsonschema.validate(m, SCHEMA)
    except jsonschema.ValidationError:
        return
    raise AssertionError("expected rejection of source='guessed'")
