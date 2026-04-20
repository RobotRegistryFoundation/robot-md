"""`robot-md calibrate --hand-eye` writes a refined extrinsic + source."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import yaml


def _write_manifest(tmp_path: Path) -> Path:
    fm = {
        "metadata": {"robot_name": "r"},
        "physics": {
            "type": "arm", "dof": 6,
            "solver": {
                "convention": "DH",
                "base_frame": {"up": "z", "forward": "x"},
                "encoder": {"steps_per_rev": 4096},
                "gripper": {"joint_id": "gripper", "tip_offset_mm": [30, 0, 0], "open_steps": 1700, "close_steps": 1200},
                "ik_provider": "inhouse-so-arm101",
                "cameras": [{
                    "driver_id": "oakd", "primary_stream": "rgb", "mount": "world",
                    "extrinsic": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    "extrinsic_source": "preset_default",
                }],
            },
            "kinematics": [
                {"id": "shoulder_pan", "axis": "z", "a_mm": 0, "d_mm": 60, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "shoulder_lift", "axis": "y", "a_mm": 125, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "elbow_flex", "axis": "y", "a_mm": 125, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_flex", "axis": "y", "a_mm": 60, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_roll", "axis": "x", "a_mm": 30, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "gripper", "axis": "y", "a_mm": 0, "d_mm": 0, "zero_pose_steps": 1200, "encoder_sign": 1},
            ],
        },
        "drivers": [{"id": "s", "protocol": "feetech", "port": "/dev/null"}],
        "capabilities": ["arm.home"],
        "safety": {"estop": {"software": True}},
    }
    p = tmp_path / "ROBOT.md"
    p.write_text("---\n" + yaml.safe_dump(fm) + "---\n\n# r\n\n")
    return p


def test_write_extrinsic_updates_manifest(tmp_path):
    from robot_md.hand_eye import write_extrinsic

    p = _write_manifest(tmp_path)
    write_extrinsic(p, six_vec=(400.0, 0.0, 300.0, 0.1, 0.2, 0.3), source="hand_eye_calibrated")

    fm = yaml.safe_load(p.read_text().split("---")[1])
    cam = fm["physics"]["solver"]["cameras"][0]
    assert cam["extrinsic_source"] == "hand_eye_calibrated"
    assert cam["extrinsic"] == pytest.approx([400.0, 0.0, 300.0, 0.1, 0.2, 0.3])


def test_cli_calibrate_hand_eye_writes_calibrated_source(tmp_path):
    """When the sweep yields a valid (R, t), write it and flip the source tag."""
    from robot_md.hand_eye import cli_calibrate_hand_eye

    p = _write_manifest(tmp_path)
    fake_R = np.eye(3)
    fake_t = np.array([400.0, 0.0, 300.0])

    with patch("robot_md.hand_eye._run_sweep") as mock_sweep:
        mock_sweep.return_value = (fake_R, fake_t)
        rc = cli_calibrate_hand_eye(
            str(p), marker_pos=(200.0, 0.0, 0.0),
            marker_size_mm=50.0, marker_id=0, dry_run=False,
        )
    assert rc == 0

    fm = yaml.safe_load(p.read_text().split("---")[1])
    cam = fm["physics"]["solver"]["cameras"][0]
    assert cam["extrinsic_source"] == "hand_eye_calibrated"
    assert cam["extrinsic"][0:3] == pytest.approx([400.0, 0.0, 300.0], abs=1e-3)


def test_cli_calibrate_hand_eye_dry_run_does_not_write(tmp_path):
    from robot_md.hand_eye import cli_calibrate_hand_eye

    p = _write_manifest(tmp_path)
    before = p.read_text()

    with patch("robot_md.hand_eye._run_sweep") as mock_sweep:
        mock_sweep.return_value = (np.eye(3), np.array([1.0, 2.0, 3.0]))
        rc = cli_calibrate_hand_eye(
            str(p), marker_pos=(200.0, 0.0, 0.0),
            marker_size_mm=50.0, marker_id=0, dry_run=True,
        )
    assert rc == 0
    assert p.read_text() == before
