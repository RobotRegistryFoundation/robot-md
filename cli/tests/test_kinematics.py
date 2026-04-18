"""Tests for the baseline kinematics solver.

Focuses on the parts that are topology-agnostic and provably correct:
- step ↔ angle round-trip honoring encoder_sign + zero_pose_steps
- loading the solver block from a parsed ROBOT.md
- FK/IK are tested only for their contract (shape of return), not for
  geometric accuracy — that depends on the chain convention and is
  verified per-robot by calibration, not here.
"""
from __future__ import annotations

import math

import pytest

from robot_md.kinematics import Joint, Kinematics, KinematicsError
from robot_md.parser import parse_text


BOB_MIN = """---
rcan_version: "3.0"
metadata:
  robot_name: bob
physics:
  type: arm+camera
  dof: 6
  solver:
    convention: DH
    base_frame: { up: z, forward: x }
    encoder:
      steps_per_rev: 4096
    gripper:
      joint_id: gripper
      tip_offset_mm: [0, 0, 30]
      open_steps: 1700
      close_steps: 1200
  kinematics:
    - { id: shoulder_pan,  axis: z, limits_deg: [-180, 180], length_mm: 60,  servo_id: 1, encoder_sign: 1,  zero_pose_steps: 2048 }
    - { id: shoulder_lift, axis: y, limits_deg: [-90, 90],   length_mm: 125, servo_id: 2, encoder_sign: 1,  zero_pose_steps: 2048 }
    - { id: elbow_flex,    axis: y, limits_deg: [-90, 90],   length_mm: 125, servo_id: 3, encoder_sign: 1,  zero_pose_steps: 2048 }
    - { id: wrist_flex,    axis: y, limits_deg: [-90, 90],   length_mm: 60,  servo_id: 4, encoder_sign: 1,  zero_pose_steps: 2048 }
    - { id: wrist_roll,    axis: x, limits_deg: [-180, 180], length_mm: 30,  servo_id: 5, encoder_sign: 1,  zero_pose_steps: 2048 }
    - { id: gripper,       axis: y, limits_deg: [0, 90],     length_mm: 40,  servo_id: 6, encoder_sign: 1,  zero_pose_steps: 1200 }
drivers:
  - { id: arm, protocol: feetech, port: /dev/ttyACM0, baud_rate: 1000000, model: STS3215, count: 6 }
safety:
  estop: { software: true, response_ms: 100 }
---

# bob

## Identity
Minimal bob for tests.

## What bob Can Do
Pick and place.

## Safety Gates
Software E-stop at 100 ms.
"""


def _kin():
    return Kinematics(parse_text(BOB_MIN).frontmatter)


def test_loads_joints_and_gripper_config():
    k = _kin()
    assert [j.id for j in k.joints] == [
        "shoulder_pan", "shoulder_lift", "elbow_flex",
        "wrist_flex", "wrist_roll", "gripper",
    ]
    assert k.gripper_joint_id == "gripper"
    assert k.gripper_tip_offset_mm == [0, 0, 30]
    assert k.gripper_open_steps == 1700
    assert k.gripper_close_steps == 1200
    # All joints picked up steps_per_rev = 4096
    assert all(j.steps_per_rev == 4096 for j in k.joints)


def test_steps_to_rad_at_zero_pose():
    """At zero_pose_steps, the joint angle must be exactly 0."""
    k = _kin()
    for j in k.joints:
        assert j.steps_to_rad(j.zero_pose_steps) == pytest.approx(0.0)


def test_step_angle_roundtrip():
    """steps → rad → steps must return the original encoder value."""
    k = _kin()
    for j in k.joints:
        for s in (0, 1000, 2048, 3000, 4095):
            rad = j.steps_to_rad(s)
            back = j.rad_to_steps(rad)
            assert back == s, f"{j.id}: {s} → {rad} → {back}"


def test_encoder_sign_inverts_direction():
    """Flipping encoder_sign should flip the sign of the derived angle."""
    k = _kin()
    j = k.by_id["shoulder_lift"]
    # Build a mirror joint with encoder_sign=-1
    mirror = Joint(
        id=j.id, axis=j.axis, a_mm=j.a_mm, d_mm=j.d_mm, limits_rad=j.limits_rad,
        servo_id=j.servo_id, encoder_sign=-1, zero_pose_steps=j.zero_pose_steps,
        steps_per_rev=j.steps_per_rev,
    )
    for s in (1000, 2048, 3000):
        assert j.steps_to_rad(s) == pytest.approx(-mirror.steps_to_rad(s))


def test_full_steps_to_angles_maps_all_joints():
    """The bulk helper covers every declared joint."""
    k = _kin()
    steps = {j.id: j.zero_pose_steps for j in k.joints}
    angles = k.steps_to_angles(steps)
    assert set(angles) == {j.id for j in k.joints}
    # All at zero pose → all angles should be zero
    for v in angles.values():
        assert v == pytest.approx(0.0)


def test_angles_to_step_targets_inverts_bulk():
    """steps_to_angles followed by angles_to_step_targets is the identity."""
    k = _kin()
    original = {"shoulder_pan": 2100, "shoulder_lift": 1900, "elbow_flex": 3700,
                "wrist_flex": 2000, "wrist_roll": 2048, "gripper": 1500}
    angles = k.steps_to_angles(original)
    back = k.angles_to_step_targets(angles)
    for k_, v in original.items():
        assert back[k_] == v


def test_fk_zero_pose_has_expected_shape():
    """At zero pose, FK returns a tuple of three floats."""
    k = _kin()
    zero = {j.id: 0.0 for j in k.joints}
    out = k.fk(zero)
    assert len(out) == 3
    assert all(isinstance(v, float) for v in out)


def test_ik_requires_known_joint_names():
    """IK should raise KinematicsError if shoulder/elbow/wrist joints aren't named."""

    class Minimal:
        pass

    bad = {
        "physics": {
            "type": "arm",
            "dof": 1,
            "kinematics": [{"id": "only_joint", "axis": "y", "length_mm": 100}],
        }
    }
    k = Kinematics(bad)
    with pytest.raises(KinematicsError):
        k.ik_reach((100, 0, 0))


def test_ik_unreachable_raises():
    """IK should raise when the target exceeds the 2-link planar reach."""
    k = _kin()
    with pytest.raises(KinematicsError):
        k.ik_reach((5000, 0, 0))  # way beyond any physical reach


def test_empty_kinematics_fails_fast():
    """A ROBOT.md with no kinematics[] must fail construction cleanly."""
    with pytest.raises(KinematicsError):
        Kinematics({"physics": {"type": "arm", "dof": 0}})
