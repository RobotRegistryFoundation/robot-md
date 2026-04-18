"""Tests for the manifest-rewrite side of `robot-md calibrate`.

Hardware-touching code (read_current_pose) is exercised by live smoke tests
against a real arm — not covered by this suite.
"""
from __future__ import annotations

import textwrap

import pytest

pytest.importorskip("ruamel.yaml")  # skip if ruamel isn't installed

from robot_md.calibrate import JointReading, write_zero_pose_to_manifest


BOB_MIN = """\
---
rcan_version: "3.0"
metadata:
  robot_name: bob
physics:
  type: arm+camera
  dof: 6
  # NOTE: this comment must survive the rewrite
  kinematics:
    - id: shoulder_pan
      axis: z
      limits_deg: [-180, 180]
      length_mm: 60
      servo_id: 1
      encoder_sign: 1
      zero_pose_steps: 2048  # placeholder — calibrate overwrites
    - id: shoulder_lift
      axis: y
      limits_deg: [-90, 90]
      length_mm: 125
      servo_id: 2
      encoder_sign: 1
      zero_pose_steps: 2048
drivers:
  - id: arm
    protocol: feetech
    port: /dev/ttyACM0
    baud_rate: 1000000
    model: STS3215
    count: 6
safety:
  estop:
    software: true
    response_ms: 100
---

# bob

## Identity
Test.

## What bob Can Do
Test.

## Safety Gates
Test.
"""


def test_writes_zero_pose_steps(tmp_path):
    p = tmp_path / "bob.ROBOT.md"
    p.write_text(BOB_MIN)
    readings = [
        JointReading("shoulder_pan", 1, 2100),
        JointReading("shoulder_lift", 2, 1755),
    ]
    n = write_zero_pose_to_manifest(p, readings)
    assert n == 2
    out = p.read_text()
    # New values landed
    assert "zero_pose_steps: 2100" in out
    assert "zero_pose_steps: 1755" in out
    # Old placeholders gone
    assert "zero_pose_steps: 2048" not in out
    # Prose body preserved verbatim
    assert "## What bob Can Do" in out
    # Top comment preserved
    assert "NOTE: this comment must survive the rewrite" in out


def test_skips_joints_with_failed_reading(tmp_path):
    p = tmp_path / "bob.ROBOT.md"
    p.write_text(BOB_MIN)
    readings = [
        JointReading("shoulder_pan", 1, None),       # read failed
        JointReading("shoulder_lift", 2, 1800),
    ]
    n = write_zero_pose_to_manifest(p, readings)
    assert n == 1
    out = p.read_text()
    # shoulder_lift updated
    assert "zero_pose_steps: 1800" in out
    # shoulder_pan should retain the original 2048
    # (check by counting 2048 appearances — should be exactly 1)
    assert out.count("zero_pose_steps: 2048") == 1


def test_unknown_joint_id_is_silent(tmp_path):
    p = tmp_path / "bob.ROBOT.md"
    p.write_text(BOB_MIN)
    readings = [JointReading("not_a_joint", 99, 1000)]
    n = write_zero_pose_to_manifest(p, readings)
    assert n == 0
    # File should be unchanged
    assert "zero_pose_steps: 2048" in p.read_text()


def test_frontmatter_roundtrip_preserves_body(tmp_path):
    p = tmp_path / "bob.ROBOT.md"
    p.write_text(BOB_MIN)
    # No-op readings
    write_zero_pose_to_manifest(p, [])
    out = p.read_text()
    # Body text after closing --- should match
    assert out.endswith(BOB_MIN.split("\n---\n", 1)[1])


def test_missing_frontmatter_raises(tmp_path):
    p = tmp_path / "bad.md"
    p.write_text("# no frontmatter here\njust prose")
    with pytest.raises(RuntimeError, match="frontmatter"):
        write_zero_pose_to_manifest(p, [])
