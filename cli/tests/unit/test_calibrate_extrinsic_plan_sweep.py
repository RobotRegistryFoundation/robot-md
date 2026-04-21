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
                "gripper": {
                    "tip_offset_mm": [30.0, 0.0, 0.0],
                    "open_steps": 1700,
                    "close_steps": 1200,
                },
            },
            "kinematics": [
                {
                    "id": "shoulder_pan",
                    "axis": "z",
                    "a_mm": 0.0,
                    "d_mm": 30.0,
                    "limits_deg": [-180, 180],
                },
                {
                    "id": "shoulder_lift",
                    "axis": "y",
                    "a_mm": 120.0,
                    "d_mm": 0.0,
                    "limits_deg": [-90, 90],
                },
                {
                    "id": "elbow_flex",
                    "axis": "y",
                    "a_mm": 120.0,
                    "d_mm": 0.0,
                    "limits_deg": [-90, 90],
                },
                {
                    "id": "wrist_flex",
                    "axis": "y",
                    "a_mm": 60.0,
                    "d_mm": 0.0,
                    "limits_deg": [-90, 90],
                },
                {
                    "id": "wrist_roll",
                    "axis": "x",
                    "a_mm": 0.0,
                    "d_mm": 30.0,
                    "limits_deg": [-180, 180],
                },
                {"id": "gripper", "axis": "y", "a_mm": 0.0, "d_mm": 0.0, "limits_deg": [-90, 90]},
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
    """No pose should trigger analyze_envelope at the transient duration plan_sweep uses."""
    from robot_md.kinematics import Kinematics

    fm = _so_arm101_fm()
    workspace = fm["physics"]["workspace"]["bounds_mm"]
    kin = Kinematics(fm)
    poses = plan_sweep(fm, workspace, n_poses=6, seed=0)
    for p in poses:
        risk = kin.analyze_envelope(p, duration_ms=200)
        assert risk.level == "ok", f"pose {p} triggers {risk.level} ({risk.reason})"


def test_plan_sweep_succeeds_with_real_so_arm101_preset():
    """Regression: plan_sweep must work with the actual so_arm101 preset —
    production joint limits (±90°), production workspace, production DH
    params. If this ever fails, the calibration subsystem is broken on
    real hardware."""
    from robot_md.init import load_presets

    presets = load_presets()
    so_arm101 = next((p for p in presets if p.name == "so_arm101"), None)
    assert so_arm101 is not None, "so_arm101 preset missing from registry"

    fm = so_arm101.data  # preset.data is the full frontmatter dict minus `match`
    workspace = fm.get("physics", {}).get("workspace", {}).get("bounds_mm")
    assert workspace is not None, "so_arm101 preset must declare physics.workspace.bounds_mm"

    poses = plan_sweep(fm, workspace, n_poses=6, seed=0)
    assert len(poses) == 6
    # Each pose must be safe under the transient envelope check that plan_sweep uses.
    from robot_md.kinematics import Kinematics

    kin = Kinematics(fm)
    for p in poses:
        risk = kin.analyze_envelope(p, duration_ms=200)
        assert risk.level == "ok", f"plan_sweep returned unsafe pose: {risk.reason}"
