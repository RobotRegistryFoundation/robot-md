"""Pre-flight envelope analysis rejects trajectories likely to latch the STS3215."""
from __future__ import annotations

import math

from robot_md.kinematics import Kinematics, KinematicsError


def _so_arm101_spec():
    """Minimal SO-ARM101 frontmatter with wrist_flex limited to ±90°."""
    return {
        "physics": {
            "solver": {
                "convention": "DH",
                "encoder": {"steps_per_rev": 4096},
                "gripper": {"joint_id": "gripper", "tip_offset_mm": [30, 0, 0]},
            },
            "kinematics": [
                {"id": "shoulder_pan",  "axis": "z", "a_mm": 0,   "d_mm": 60, "limits_deg": [-180, 180], "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "shoulder_lift", "axis": "y", "a_mm": 125, "d_mm": 0,  "limits_deg": [-180, 180], "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "elbow_flex",    "axis": "y", "a_mm": 125, "d_mm": 0,  "limits_deg": [-180, 180], "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_flex",    "axis": "y", "a_mm": 60,  "d_mm": 0,  "limits_deg": [-90, 90],   "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_roll",    "axis": "x", "a_mm": 0,   "d_mm": 0,  "limits_deg": [-180, 180], "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "gripper",       "axis": "y", "a_mm": 0,   "d_mm": 0,  "limits_deg": [-180, 180], "zero_pose_steps": 1200, "encoder_sign": 1},
            ],
        },
    }


def test_analyze_envelope_ok_for_neutral_config():
    kin = Kinematics(_so_arm101_spec())
    cfg = {j.id: 0.0 for j in kin.joints}  # all at zero (center)
    risk = kin.analyze_envelope(cfg, duration_ms=1000)
    assert risk.level == "ok"


def test_analyze_envelope_latch_warning_near_limit():
    kin = Kinematics(_so_arm101_spec())
    # Drive wrist_flex to 89° when limit is ±90° → 89/90 = 0.988 > 0.85.
    cfg = {j.id: 0.0 for j in kin.joints}
    cfg["wrist_flex"] = math.radians(89)
    risk = kin.analyze_envelope(cfg, duration_ms=1000)
    assert risk.level == "latch_warning"
    assert risk.joint == "wrist_flex"


def test_analyze_envelope_out_of_limits():
    kin = Kinematics(_so_arm101_spec())
    cfg = {j.id: 0.0 for j in kin.joints}
    cfg["wrist_flex"] = math.radians(100)  # past ±90°
    risk = kin.analyze_envelope(cfg, duration_ms=1000)
    assert risk.level == "out_of_limits"
    assert risk.joint == "wrist_flex"


def test_analyze_envelope_safe_below_threshold():
    kin = Kinematics(_so_arm101_spec())
    cfg = {j.id: 0.0 for j in kin.joints}
    cfg["wrist_flex"] = math.radians(70)  # 70/90 = 0.77 < 0.85
    risk = kin.analyze_envelope(cfg, duration_ms=1000)
    assert risk.level == "ok"


def test_analyze_envelope_short_transient_allowed():
    """A brief high-angle pose is OK — only sustained holding is risky."""
    kin = Kinematics(_so_arm101_spec())
    cfg = {j.id: 0.0 for j in kin.joints}
    cfg["wrist_flex"] = math.radians(89)
    risk = kin.analyze_envelope(cfg, duration_ms=200)  # transient
    assert risk.level == "ok"
