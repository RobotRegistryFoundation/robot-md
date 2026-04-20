"""Sweep planner generates a small set of gripper-visible joint configs."""
from __future__ import annotations

from robot_md.calibrate_extrinsic import plan_sweep


# Inline SO-ARM101-like frontmatter — shared fixture lacks physics.kinematics[].
def _so_arm101_fm():
    return {
        "physics": {
            "solver": {
                "convention": "DH",
                "encoder": {"steps_per_rev": 4096},
                "gripper": {"tip_offset_mm": [30.0, 0.0, 0.0], "open_steps": 1700, "close_steps": 1200},
            },
            "kinematics": [
                {"id": "shoulder_pan",   "axis": "z", "a_mm": 0.0,   "d_mm": 30.0, "limits_deg": [-180, 180]},
                {"id": "shoulder_lift",  "axis": "y", "a_mm": 120.0, "d_mm": 0.0,  "limits_deg": [-120, 120]},
                {"id": "elbow_flex",     "axis": "y", "a_mm": 120.0, "d_mm": 0.0,  "limits_deg": [-90, 90]},
                {"id": "wrist_flex",     "axis": "y", "a_mm": 60.0,  "d_mm": 0.0,  "limits_deg": [-120, 120]},
                {"id": "wrist_roll",     "axis": "x", "a_mm": 0.0,   "d_mm": 30.0, "limits_deg": [-180, 180]},
                {"id": "gripper",        "axis": "y", "a_mm": 0.0,   "d_mm": 0.0,  "limits_deg": [-90, 90]},
            ],
            "workspace": {"bounds_mm": {"x": [-200, 340], "y": [-340, 340], "z": [0, 250]}},
        }
    }


def test_plan_sweep_returns_requested_n_poses():
    fm = _so_arm101_fm()
    workspace = fm["physics"]["workspace"]["bounds_mm"]
    poses = plan_sweep(fm, workspace, n_poses=6, seed=0)
    assert len(poses) == 6
    for p in poses:
        assert isinstance(p, dict)
        assert "shoulder_pan" in p
        assert "wrist_flex" in p


def test_plan_sweep_all_poses_inside_workspace():
    from robot_md.kinematics import Kinematics
    fm = _so_arm101_fm()
    workspace = fm["physics"]["workspace"]["bounds_mm"]
    kin = Kinematics(fm)
    poses = plan_sweep(fm, workspace, n_poses=6, seed=0)
    for p in poses:
        x, y, z = kin.fk(p)
        assert workspace["x"][0] <= x <= workspace["x"][1]
        assert workspace["y"][0] <= y <= workspace["y"][1]
        assert workspace["z"][0] <= z <= workspace["z"][1]


def test_plan_sweep_is_deterministic():
    fm = _so_arm101_fm()
    workspace = fm["physics"]["workspace"]["bounds_mm"]
    a = plan_sweep(fm, workspace, n_poses=6, seed=42)
    b = plan_sweep(fm, workspace, n_poses=6, seed=42)
    assert a == b


def test_plan_sweep_respects_envelope():
    """No generated pose should trigger analyze_envelope latch_warning."""
    from robot_md.kinematics import Kinematics
    fm = _so_arm101_fm()
    workspace = fm["physics"]["workspace"]["bounds_mm"]
    kin = Kinematics(fm)
    poses = plan_sweep(fm, workspace, n_poses=6, seed=0)
    for p in poses:
        risk = kin.analyze_envelope(p, duration_ms=1000)
        assert risk.level == "ok", f"pose {p} triggers {risk.level} ({risk.reason})"
