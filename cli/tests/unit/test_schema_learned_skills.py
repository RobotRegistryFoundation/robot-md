from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "src/robot_md/schemas/v1/robot.schema.json").read_text()
)


def _m(extra: dict) -> dict:
    return {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "bob"},
        "physics": {"type": "arm", "dof": 6},
        "drivers": [{"id": "arm", "protocol": "feetech"}],
        "capabilities": ["status.report"],
        "safety": {"estop": {"software": True, "response_ms": 100}},
        **extra,
    }


def test_learned_skills_optional():
    jsonschema.validate(_m({}), SCHEMA)


def test_learned_skills_accepts_entry():
    jsonschema.validate(
        _m(
            {
                "learned_skills": [
                    {
                        "id": "red_lego_pick.2026-04-19",
                        "status": "blocked",
                        "validated": ["scene_capture"],
                        "blocked_by": ["forward_home_pose_missing"],
                        "notes": "Vision chain works.",
                    }
                ]
            }
        ),
        SCHEMA,
    )


def test_learned_skills_status_enum_rejected():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_m({"learned_skills": [{"id": "x", "status": "excellent"}]}), SCHEMA)


def test_learned_skills_requires_id():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _m(
                {
                    "learned_skills": [{"status": "ok"}]  # missing id
                }
            ),
            SCHEMA,
        )


def test_learned_skills_accepts_all_three_statuses():
    for status in ["ok", "blocked", "degraded"]:
        jsonschema.validate(
            _m({"learned_skills": [{"id": f"s.{status}", "status": status}]}), SCHEMA
        )
