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


def test_workspace_declared_with_bounds():
    data = _load()
    ws = data["physics"].get("workspace")
    assert ws is not None
    bounds = ws.get("bounds_mm")
    assert bounds is not None
    for axis in ("x", "y", "z"):
        assert axis in bounds
        lo, hi = bounds[axis]
        assert lo < hi


def test_workspace_covers_default_ready_target():
    """Target (200, 0, 50) must be inside declared workspace."""
    data = _load()
    bounds = data["physics"]["workspace"]["bounds_mm"]
    assert bounds["x"][0] <= 200 <= bounds["x"][1]
    assert bounds["y"][0] <= 0 <= bounds["y"][1]
    assert bounds["z"][0] <= 50 <= bounds["z"][1]


def test_capability_contracts_arm_pick():
    data = _load()
    contracts = data.get("capability_contracts") or {}
    pick = contracts.get("arm.pick")
    assert pick is not None
    precondition_kinds = [p.get("kind") for p in pick.get("preconditions", [])]
    assert set(precondition_kinds) >= {
        "pose_taught",
        "extrinsic_present",
        "ik_provider_set",
        "workspace_declared",
        "backend_resolved",
    }


def test_capability_contracts_arm_place():
    data = _load()
    contracts = data.get("capability_contracts") or {}
    place = contracts.get("arm.place")
    assert place is not None


def test_capability_contracts_arm_home():
    data = _load()
    contracts = data.get("capability_contracts") or {}
    home = contracts.get("arm.home")
    assert home is not None
    kinds = [p.get("kind") for p in home.get("preconditions", [])]
    assert "pose_taught" in kinds
