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
        "capabilities": ["vision.find", "status.report"],
        "safety": {"estop": {"software": True, "response_ms": 100}},
        **extra,
    }


def test_object_descriptors_optional():
    jsonschema.validate(_m({}), SCHEMA)


def test_object_descriptors_hsv_entry():
    jsonschema.validate(_m({
        "vision": {
            "object_descriptors": [
                {
                    "id": "red_lego",
                    "detector": "hsv",
                    "params": {"h_ranges": [[0, 10], [170, 180]], "s_min": 110, "v_min": 80},
                }
            ]
        }
    }), SCHEMA)


def test_object_descriptors_hsv_roi_entry():
    jsonschema.validate(_m({
        "vision": {
            "object_descriptors": [
                {
                    "id": "white_bowl",
                    "detector": "hsv_roi",
                    "params": {
                        "s_max": 80, "v_min": 100,
                        "roi": {"u_max": 450, "v_max": 360},
                    },
                }
            ]
        }
    }), SCHEMA)


def test_object_descriptors_rejects_unknown_detector():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_m({
            "vision": {"object_descriptors": [{"id": "x", "detector": "magic", "params": {}}]}
        }), SCHEMA)


def test_object_descriptors_requires_id_detector_params():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_m({
            "vision": {"object_descriptors": [{"id": "x", "detector": "hsv"}]}  # missing params
        }), SCHEMA)
