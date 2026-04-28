from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


_SCHEMA_PATH = Path(__file__).parents[2] / "src" / "robot_md" / "schemas" / "capabilities.json"


def _load_def(name: str) -> dict:
    schema = json.loads(_SCHEMA_PATH.read_text())
    return schema["definitions"][name]


def test_arm_pick_accepts_minimal_valid_args() -> None:
    jsonschema.validate({"target": "red_lego"}, _load_def("arm.pick"))


def test_arm_pick_rejects_missing_target() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({}, _load_def("arm.pick"))


def test_arm_pick_rejects_wrong_target_type() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"target": 42}, _load_def("arm.pick"))


def test_arm_home_rejects_extra_properties() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"surprise": True}, _load_def("arm.home"))
