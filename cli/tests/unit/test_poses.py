"""RobotSpec parses physics.poses into PoseDef dict."""
from __future__ import annotations

import yaml

from robot_md.parser import parse_text
from robot_md.poses import write_pose_to_manifest
from robot_md.robot_spec import RobotSpec


def _with_poses() -> str:
    return """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics:
  type: arm
  dof: 6
  poses:
    ready:
      description: 'extended forward'
      joints: {shoulder_pan: 2048, shoulder_lift: 1600}
      source: taught
      taught_at: '2026-04-19'
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""


def test_spec_surfaces_pose_ready():
    spec = RobotSpec.from_parsed(parse_text(_with_poses()))
    assert "ready" in spec.physics.poses
    ready = spec.physics.poses["ready"]
    assert ready.joints["shoulder_pan"] == 2048
    assert ready.joints["shoulder_lift"] == 1600
    assert ready.source == "taught"


def test_spec_poses_empty_when_absent():
    minimal = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(minimal))
    assert spec.physics.poses == {}


def test_write_pose_inserts_ready_block(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech}]\n"
        "capabilities: [status.report]\n"
        "safety: {estop: {software: true, response_ms: 100}}\n"
        "---\n# bob\n"
    )
    write_pose_to_manifest(
        manifest,
        name="ready",
        joints={"shoulder_pan": 2048, "shoulder_lift": 1600},
        description="extended forward",
    )
    fm = yaml.safe_load(manifest.read_text().split("---")[1])
    poses = fm["physics"]["poses"]
    assert poses["ready"]["joints"]["shoulder_lift"] == 1600
    assert poses["ready"]["source"] == "taught"
    assert "taught_at" in poses["ready"]


def test_write_pose_overwrites_existing(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics:\n"
        "  type: arm\n  dof: 6\n"
        "  poses: {ready: {joints: {shoulder_pan: 100}, source: taught}}\n"
        "drivers: [{id: arm, protocol: feetech}]\n"
        "capabilities: [status.report]\n"
        "safety: {estop: {software: true, response_ms: 100}}\n"
        "---\n# bob\n"
    )
    write_pose_to_manifest(manifest, name="ready", joints={"shoulder_pan": 999})
    fm = yaml.safe_load(manifest.read_text().split("---")[1])
    assert fm["physics"]["poses"]["ready"]["joints"]["shoulder_pan"] == 999


def test_spec_surfaces_capability_contracts():
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [arm.pick, status.report]
capability_contracts:
  arm.pick:
    preconditions:
      - {kind: pose_taught, name: ready}
      - {kind: extrinsic_present}
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(text))
    assert "arm.pick" in spec.capability_contracts
    pre = spec.capability_contracts["arm.pick"].preconditions
    assert pre[0].kind == "pose_taught"
    assert pre[0].name == "ready"
    assert pre[1].kind == "extrinsic_present"


def test_spec_capability_contracts_empty_when_absent():
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(text))
    assert spec.capability_contracts == {}


def test_spec_surfaces_object_descriptors():
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [vision.find, status.report]
vision:
  object_descriptors:
    - id: red_lego
      detector: hsv
      params:
        h_ranges: [[0, 10], [170, 180]]
        s_min: 110
        v_min: 80
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(text))
    descs = spec.vision.object_descriptors
    assert descs[0].id == "red_lego"
    assert descs[0].detector == "hsv"
    assert descs[0].params["s_min"] == 110


def test_spec_vision_find_returns_descriptor():
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [vision.find]
vision:
  object_descriptors:
    - id: red_lego
      detector: hsv
      params: {h_ranges: [[0,10]], s_min: 110, v_min: 80}
    - id: white_bowl
      detector: hsv_roi
      params: {s_max: 80, v_min: 100, roi: {u_max: 450, v_max: 360}}
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(text))
    red = spec.vision.find("red_lego")
    assert red is not None
    assert red.detector == "hsv"
    bowl = spec.vision.find("white_bowl")
    assert bowl is not None
    assert bowl.params["s_max"] == 80
    assert spec.vision.find("nonexistent") is None


def test_spec_vision_empty_when_absent():
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(text))
    assert spec.vision.object_descriptors == ()
    assert spec.vision.find("anything") is None


def test_spec_surfaces_learned_skills():
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
learned_skills:
  - id: red_lego_pick.2026-04-19
    status: blocked
    validated: [scene_capture, hsv_red]
    blocked_by: [forward_home_pose_missing]
    notes: 'Vision chain works.'
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(text))
    ls = spec.learned_skills
    assert len(ls) == 1
    assert ls[0].id == "red_lego_pick.2026-04-19"
    assert ls[0].status == "blocked"
    assert "hsv_red" in ls[0].validated
    assert "forward_home_pose_missing" in ls[0].blocked_by
    assert ls[0].notes == "Vision chain works."


def test_spec_learned_skills_empty_when_absent():
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(text))
    assert spec.learned_skills == ()


def test_spec_learned_skills_defaults():
    """Minimal entry (only id) should yield default status, empty tuples."""
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
learned_skills:
  - id: minimal
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(text))
    s = spec.learned_skills[0]
    assert s.id == "minimal"
    assert s.status == "ok"
    assert s.validated == ()
    assert s.blocked_by == ()
    assert s.notes is None
    assert s.recorded_at is None
