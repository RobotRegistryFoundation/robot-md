"""Hand-eye calibration: ArUco pose sampling + cv2.calibrateHandEye wrapper."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def test_calibrate_hand_eye_invokes_cv2_with_samples(tmp_path):
    """Given 8 samples of (robot_pose, marker_pose), call cv2.calibrateHandEye."""
    from robot_md.hand_eye import calibrate_from_samples

    R_gripper2base = [np.eye(3) for _ in range(8)]
    t_gripper2base = [np.array([i * 10.0, 0.0, 0.0]) for i in range(8)]
    R_target2cam = [np.eye(3) for _ in range(8)]
    t_target2cam = [np.array([100.0, 0.0, 200.0]) for _ in range(8)]

    with patch("cv2.calibrateHandEye") as mock_calib:
        mock_calib.return_value = (np.eye(3), np.array([[10.0], [20.0], [30.0]]))
        R, t = calibrate_from_samples(
            R_gripper2base=R_gripper2base,
            t_gripper2base=t_gripper2base,
            R_target2cam=R_target2cam,
            t_target2cam=t_target2cam,
        )
    mock_calib.assert_called_once()
    assert R.shape == (3, 3)
    assert t.shape == (3,) or t.shape == (3, 1)


def test_calibrate_requires_at_least_3_samples():
    from robot_md.hand_eye import calibrate_from_samples

    with pytest.raises(ValueError, match="at least 3"):
        calibrate_from_samples(
            R_gripper2base=[np.eye(3), np.eye(3)],
            t_gripper2base=[np.zeros(3), np.zeros(3)],
            R_target2cam=[np.eye(3), np.eye(3)],
            t_target2cam=[np.zeros(3), np.zeros(3)],
        )


def test_detect_marker_returns_pose_from_frame():
    """Given an RGB frame with a visible ArUco marker, return (R, t) in camera frame."""
    from robot_md.hand_eye import detect_marker_pose

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    K = np.array([[500.0, 0, 320], [0, 500, 240], [0, 0, 1]])
    dist = np.zeros(5)

    with patch("cv2.aruco.ArucoDetector", create=True) as mock_det_cls:
        mock_det = MagicMock()
        mock_det.detectMarkers.return_value = (
            [np.array([[[100, 100], [200, 100], [200, 200], [100, 200]]], dtype=np.float32)],
            np.array([[0]]),
            [],
        )
        mock_det_cls.return_value = mock_det
        with patch("cv2.aruco.estimatePoseSingleMarkers", create=True) as mock_pose:
            mock_pose.return_value = (
                np.array([[[0.0, 0.0, 0.0]]]),
                np.array([[[0.0, 0.0, 500.0]]]),
                None,
            )
            result = detect_marker_pose(frame, K=K, dist_coeffs=dist, marker_id=0, marker_size_mm=50.0)
    assert result is not None
    R, t = result
    assert R.shape == (3, 3)
    assert t.shape == (3,)


def test_detect_marker_returns_none_when_marker_absent():
    from robot_md.hand_eye import detect_marker_pose

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    K = np.eye(3)
    dist = np.zeros(5)

    with patch("cv2.aruco.ArucoDetector", create=True) as mock_det_cls:
        mock_det = MagicMock()
        mock_det.detectMarkers.return_value = ([], None, [])
        mock_det_cls.return_value = mock_det
        result = detect_marker_pose(frame, K=K, dist_coeffs=dist, marker_id=0, marker_size_mm=50.0)
    assert result is None
