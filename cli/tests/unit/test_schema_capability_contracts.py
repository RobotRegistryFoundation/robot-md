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
        "capabilities": ["arm.pick", "status.report"],
        "safety": {"estop": {"software": True, "response_ms": 100}},
        **extra,
    }


def test_contracts_block_is_optional():
    jsonschema.validate(_m({}), SCHEMA)


def test_contracts_accepts_precondition_list():
    jsonschema.validate(
        _m(
            {
                "capability_contracts": {
                    "arm.pick": {
                        "preconditions": [
                            {"kind": "pose_taught", "name": "ready"},
                            {"kind": "extrinsic_present"},
                        ]
                    }
                }
            }
        ),
        SCHEMA,
    )


def test_contracts_rejects_unknown_precondition_kind():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _m(
                {
                    "capability_contracts": {
                        "arm.pick": {"preconditions": [{"kind": "wishful_thinking"}]}
                    }
                }
            ),
            SCHEMA,
        )
