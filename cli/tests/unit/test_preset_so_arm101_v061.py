"""v0.6.1: so_arm101 preset ships with default extrinsic and IK provider."""
from __future__ import annotations

from pathlib import Path

import yaml

PRESET = Path(__file__).resolve().parents[2] / "src" / "robot_md" / "presets" / "so_arm101.yaml"


def _load() -> dict:
    with PRESET.open() as f:
        return yaml.safe_load(f)


def test_solver_declares_inhouse_ik_provider():
    data = _load()
    solver = data["physics"]["solver"]
    assert solver.get("ik_provider") == "inhouse-so-arm101"


def test_solver_declares_ik_frame_ready():
    data = _load()
    solver = data["physics"]["solver"]
    assert solver.get("ik_frame") == "ready"


def test_cameras_has_default_extrinsic():
    data = _load()
    cams = data["physics"]["solver"].get("cameras") or []
    assert len(cams) >= 1, "preset must declare at least one camera"
    ext = cams[0].get("extrinsic")
    assert ext is not None and len(ext) == 6


def test_cameras_has_extrinsic_source_preset_default():
    data = _load()
    cams = data["physics"]["solver"]["cameras"]
    assert cams[0].get("extrinsic_source") == "preset_default"


def test_robot_spec_round_trip_preserves_extrinsic_source():
    """Parsing the preset into RobotSpec preserves the new field."""
    from robot_md.parser import ParsedRobotMd
    from robot_md.robot_spec import RobotSpec

    data = _load()
    data["metadata"] = {"robot_name": "test-robot"}
    parsed = ParsedRobotMd(frontmatter=data, body="")
    spec = RobotSpec.from_parsed(parsed)
    cams = spec.physics.cameras
    assert len(cams) >= 1
    assert cams[0].extrinsic_source == "preset_default"
