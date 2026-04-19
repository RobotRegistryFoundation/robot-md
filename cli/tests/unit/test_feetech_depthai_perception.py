from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from robot_md.parser import parse_file
from robot_md.robot_spec import RobotSpec


def _spec(fixtures_dir):
    return RobotSpec.from_parsed(parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml"))


def _install_fakes(monkeypatch):
    """Stand-in for depthai, just enough for perception tests."""
    import numpy as np

    fake_dai = MagicMock()

    # Calibration readout: return an intrinsic matrix
    fake_cal = MagicMock()
    fake_cal.getCameraIntrinsics.return_value = [
        [860.0, 0.0, 640.0],
        [0.0, 860.0, 360.0],
        [0.0, 0.0, 1.0],
    ]
    fake_cal_device = MagicMock()
    fake_cal_device.readCalibration.return_value = fake_cal
    fake_dai.Device.return_value.__enter__.return_value = fake_cal_device
    fake_dai.Device.return_value.__exit__.return_value = False
    fake_dai.CameraBoardSocket.CAM_A = "CAM_A"
    fake_dai.CameraBoardSocket.CAM_B = "CAM_B"
    fake_dai.CameraBoardSocket.CAM_C = "CAM_C"

    # Pipeline context manager
    fake_rgb_msg = MagicMock()
    fake_rgb_msg.getCvFrame.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)
    fake_depth_msg = MagicMock()
    fake_depth_msg.getFrame.return_value = np.full((720, 1280), 400, dtype=np.uint16)

    fake_rgb_q = MagicMock(); fake_rgb_q.get.return_value = fake_rgb_msg
    fake_depth_q = MagicMock(); fake_depth_q.get.return_value = fake_depth_msg

    fake_pipe = MagicMock()
    fake_pipe.__enter__.return_value = fake_pipe
    fake_pipe.__exit__.return_value = False
    fake_pipe.start.return_value = None

    fake_rgb_cam = MagicMock()
    fake_rgb_cam_out = MagicMock()
    fake_rgb_cam_out.createOutputQueue.return_value = fake_rgb_q
    fake_rgb_cam.requestOutput.return_value = fake_rgb_cam_out
    fake_rgb_cam.build.return_value = fake_rgb_cam

    fake_cam_left = MagicMock(); fake_cam_left.build.return_value = fake_cam_left
    fake_cam_right = MagicMock(); fake_cam_right.build.return_value = fake_cam_right
    fake_cam_left_out = MagicMock()
    fake_cam_right_out = MagicMock()
    fake_cam_left.requestOutput.return_value = fake_cam_left_out
    fake_cam_right.requestOutput.return_value = fake_cam_right_out

    fake_stereo = MagicMock()
    fake_stereo_depth = MagicMock()
    fake_stereo_depth.createOutputQueue.return_value = fake_depth_q
    fake_stereo.depth = fake_stereo_depth

    fake_pipe.create.side_effect = [fake_rgb_cam, fake_cam_left, fake_cam_right, fake_stereo]

    fake_dai.Pipeline.return_value = fake_pipe
    fake_dai.node = MagicMock()
    fake_dai.node.Camera = MagicMock()
    fake_dai.node.StereoDepth = MagicMock()
    fake_dai.node.StereoDepth.PresetMode.FAST_ACCURACY = "FAST_ACCURACY"
    fake_dai.ImgFrame.Type.NV12 = "NV12"

    monkeypatch.setitem(sys.modules, "depthai", fake_dai)
    return fake_dai


def test_open_reads_intrinsics(monkeypatch, fixtures_dir):
    _install_fakes(monkeypatch)
    from robot_md.backends.feetech_depthai.perception import Perception

    p = Perception.from_spec(_spec(fixtures_dir))
    p.open()
    assert p.K is not None
    assert p.K.shape == (3, 3)
    assert p.K[0, 0] == 860.0
    p.close()


def test_grab_frame_returns_rgb_depth_k(monkeypatch, fixtures_dir):
    import numpy as np
    _install_fakes(monkeypatch)
    from robot_md.backends.feetech_depthai.perception import Perception

    p = Perception.from_spec(_spec(fixtures_dir))
    p.open()
    rgb, depth, K = p.grab_frame()
    assert isinstance(rgb, np.ndarray) and rgb.shape == (720, 1280, 3)
    assert isinstance(depth, np.ndarray) and depth.shape == (720, 1280)
    assert K.shape == (3, 3)
    p.close()


def test_pixel_to_3d_math():
    import numpy as np
    from robot_md.backends.feetech_depthai.perception import _pixel_to_3d

    K = np.array([[860.0, 0.0, 640.0], [0.0, 860.0, 360.0], [0.0, 0.0, 1.0]])
    x, y, z = _pixel_to_3d(640, 360, 500.0, K)
    assert abs(x) < 1e-6 and abs(y) < 1e-6 and z == 500.0

    x, y, z = _pixel_to_3d(840, 360, 1000.0, K)
    assert abs(x - 200 * 1000 / 860) < 1e-3


def test_pixel_to_3d_zero_depth_is_nan():
    import math
    import numpy as np
    from robot_md.backends.feetech_depthai.perception import _pixel_to_3d
    K = np.eye(3)
    x, y, z = _pixel_to_3d(10, 10, 0.0, K)
    assert math.isnan(x) and math.isnan(y) and math.isnan(z)


def test_open_without_depthai_raises_clean_error(monkeypatch, fixtures_dir):
    monkeypatch.setitem(sys.modules, "depthai", None)
    from robot_md.backends.feetech_depthai.perception import Perception

    p = Perception.from_spec(_spec(fixtures_dir))
    with pytest.raises(RuntimeError, match="depthai"):
        p.open()
