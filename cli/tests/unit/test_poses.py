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
