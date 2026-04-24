"""Schema: camera intrinsic block + cameras[] cross-reference."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from robot_md.parser import parse_file


def _schema() -> dict:
    # Load schema directly from the file system without caching
    schema_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "robot_md"
        / "schemas"
        / "v1"
        / "robot.schema.json"
    )
    with open(schema_path) as f:
        return json.load(f)


def test_intrinsic_required_fields_accepted(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    jsonschema.Draft202012Validator(_schema()).validate(parsed.frontmatter)


def test_intrinsic_missing_fx_rejected(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["drivers"][1]["streams"]["rgb"]["intrinsic"].pop("fx")
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        jsonschema.Draft202012Validator(_schema()).validate(parsed.frontmatter)
    # Walk sub-errors (from the oneOf branch) to find the `fx` required-field violation
    messages = [str(exc_info.value)] + [str(e) for e in exc_info.value.context]
    assert any("fx" in m for m in messages), f"expected 'fx' in the error chain, got:\n{messages!r}"


def test_distortion_model_enum(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["drivers"][1]["streams"]["rgb"]["intrinsic"]["distortion_model"] = "bogus"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(parsed.frontmatter)


def test_plumb_bob_requires_5_coeffs(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["drivers"][1]["streams"]["rgb"]["intrinsic"]["distortion_coeffs"] = [0.0]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(parsed.frontmatter)


def test_depth_stream_derived_from_allowed():
    """A minimal driver with a depth stream using `derived_from` validates."""
    minimal = {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "d"},
        "physics": {"type": "arm+camera", "dof": 1},
        "drivers": [
            {
                "id": "cam",
                "protocol": "depthai",
                "streams": {
                    "left": {"intrinsic": None},
                    "right": {"intrinsic": None},
                    "depth": {"derived_from": ["left", "right"]},
                },
            }
        ],
        "safety": {"estop": {"software": True, "response_ms": 100}},
    }
    jsonschema.Draft202012Validator(_schema()).validate(minimal)


def test_depth_stream_without_derived_from_or_intrinsic_allowed():
    """An empty stream entry is technically valid (intrinsic defaults to absent)."""
    minimal = {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "d"},
        "physics": {"type": "arm+camera", "dof": 1},
        "drivers": [
            {
                "id": "cam",
                "protocol": "depthai",
                "streams": {"depth": {}},
            }
        ],
        "safety": {"estop": {"software": True, "response_ms": 100}},
    }
    jsonschema.Draft202012Validator(_schema()).validate(minimal)


def test_physics_type_arm_manipulator_allowed():
    """v1.1.1 — physics.type accepts 'arm_manipulator' (matches rcan-spec R6 draft)."""
    minimal = {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "bob"},
        "physics": {"type": "arm_manipulator", "dof": 6},
        "drivers": [{"id": "arm", "protocol": "feetech_scs"}],
        "safety": {"estop": {"software": True, "response_ms": 50}},
    }
    jsonschema.Draft202012Validator(_schema()).validate(minimal)


def test_physics_type_unknown_still_rejected():
    """v1.1.1 — unknown physics.type values still fail validation."""
    bad = {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "bob"},
        "physics": {"type": "not-a-real-type", "dof": 6},
        "drivers": [{"id": "arm", "protocol": "feetech_scs"}],
        "safety": {"estop": {"software": True, "response_ms": 50}},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(bad)


def test_stream_key_unknown_rejected(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["drivers"][1]["streams"]["BOGUS"] = {"intrinsic": None}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(parsed.frontmatter)
