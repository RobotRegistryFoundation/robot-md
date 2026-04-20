"""Doctor warns (not errors) when extrinsic is a preset default."""
from __future__ import annotations

from pathlib import Path

import yaml

from robot_md.doctor import run_all


def _write(tmp_path: Path, source: str | None, *, include_camera: bool = True) -> Path:
    fm = {
        "metadata": {"robot_name": "r"},
        "physics": {
            "type": "arm", "dof": 1,
            "solver": {
                "convention": "DH",
                "base_frame": {"up": "z", "forward": "x"},
                "encoder": {"steps_per_rev": 4096},
                "gripper": {"joint_id": "g", "tip_offset_mm": [0, 0, 0], "open_steps": 1700, "close_steps": 1200},
            },
            "kinematics": [{"id": "g", "axis": "y", "a_mm": 0, "d_mm": 0, "zero_pose_steps": 1200, "encoder_sign": 1}],
        },
        "drivers": [{"id": "s", "protocol": "feetech", "port": "/dev/null"}],
        "capabilities": [],
        "safety": {"estop": {"software": True}},
    }
    if include_camera:
        cam = {"driver_id": "o", "primary_stream": "rgb", "mount": "world",
               "extrinsic": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}
        if source is not None:
            cam["extrinsic_source"] = source
        fm["physics"]["solver"]["cameras"] = [cam]
    p = tmp_path / "ROBOT.md"
    p.write_text("---\n" + yaml.safe_dump(fm) + "---\n\n# r\n\n")
    return p


def test_doctor_warns_when_extrinsic_source_is_preset_default(tmp_path):
    p = _write(tmp_path, "preset_default")
    results = run_all(p)
    warn = next((r for r in results if r.name == "extrinsic source"), None)
    assert warn is not None
    assert warn.status == "warn"
    assert "--extrinsic" in warn.detail.lower()


def test_doctor_silent_when_extrinsic_source_hand_eye_calibrated(tmp_path):
    p = _write(tmp_path, "hand_eye_calibrated")
    results = run_all(p)
    entries = [r for r in results if r.name == "extrinsic source"]
    assert all(r.status != "warn" for r in entries)


def test_doctor_silent_when_no_cameras(tmp_path):
    """Robots without cameras don't care about extrinsic_source."""
    p = _write(tmp_path, None, include_camera=False)
    results = run_all(p)
    entries = [r for r in results if r.name == "extrinsic source"]
    assert all(r.status != "warn" for r in entries)
