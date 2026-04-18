from __future__ import annotations

import dataclasses

import pytest

from robot_md.parser import parse_file
from robot_md.robot_spec import RobotSpec


def test_build_from_parsed(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    spec = RobotSpec.from_parsed(parsed)
    assert spec.metadata.robot_name == "test-bot"
    assert "arm.pick" in spec.capabilities
    assert spec.physics.dof == 6
    assert {d.id for d in spec.drivers} == {"arm_servos", "oak-d-1"}
    oak = next(d for d in spec.drivers if d.id == "oak-d-1")
    assert "rgb" in oak.streams
    assert oak.streams["rgb"].intrinsic is not None
    assert oak.streams["rgb"].intrinsic.fx == 860.2
    # depth stream has derived_from but no intrinsic
    depth = oak.streams["depth"]
    assert depth.intrinsic is None
    assert depth.derived_from == ("left", "right")


def test_frozen(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    spec = RobotSpec.from_parsed(parsed)
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.metadata.robot_name = "nope"  # type: ignore


def test_safety_workspace_bounds_none_when_absent(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    spec = RobotSpec.from_parsed(parsed)
    assert spec.safety.workspace_bounds_m is None


def test_brain_none_when_absent(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    spec = RobotSpec.from_parsed(parsed)
    assert spec.brain is None


def test_brain_populated_when_present(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["brain"] = {
        "planning": {"provider": "anthropic", "model": "claude-opus-4-7", "confidence_gate": 0.6}
    }
    spec = RobotSpec.from_parsed(parsed)
    assert spec.brain is not None
    assert spec.brain.planning_provider == "anthropic"
    assert spec.brain.planning_confidence_gate == 0.6
    assert spec.brain.planning_timeout_ms == 30000  # default


def test_solver_cameras_populated(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    spec = RobotSpec.from_parsed(parsed)
    cams = spec.physics.cameras
    assert len(cams) == 1
    assert cams[0].driver_id == "oak-d-1"
    assert cams[0].primary_stream == "rgb"
    assert cams[0].extrinsic is None
