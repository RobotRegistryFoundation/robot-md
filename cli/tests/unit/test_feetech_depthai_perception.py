from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from robot_md.parser import parse_file
from robot_md.robot_spec import RobotSpec


def _spec(fixtures_dir):
    return RobotSpec.from_parsed(parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml"))


def _install_fakes(monkeypatch):
    """Stand-in for depthai (v2 API), just enough for perception tests."""
    import numpy as np

    fake_dai = MagicMock()

    # Calibration readout: return an intrinsic matrix
    fake_cal = MagicMock()
    fake_cal.getCameraIntrinsics.return_value = [
        [860.0, 0.0, 640.0],
        [0.0, 860.0, 360.0],
        [0.0, 0.0, 1.0],
    ]

    fake_rgb_msg = MagicMock()
    fake_rgb_msg.getCvFrame.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)
    fake_depth_msg = MagicMock()
    fake_depth_msg.getFrame.return_value = np.full((720, 1280), 400, dtype=np.uint16)

    fake_rgb_q = MagicMock()
    fake_rgb_q.get.return_value = fake_rgb_msg
    fake_depth_q = MagicMock()
    fake_depth_q.get.return_value = fake_depth_msg

    # v2: Device(pipeline) is the context manager; output queues hang off the
    # device by stream name, not off the pipeline nodes.
    fake_device = MagicMock()
    fake_device.readCalibration.return_value = fake_cal
    fake_device.getOutputQueue.side_effect = lambda name, **kw: {
        "rgb": fake_rgb_q,
        "depth": fake_depth_q,
    }[name]
    fake_dai.Device.return_value.__enter__.return_value = fake_device
    fake_dai.Device.return_value.__exit__.return_value = False
    fake_dai.CameraBoardSocket.CAM_A = "CAM_A"
    fake_dai.CameraBoardSocket.CAM_B = "CAM_B"
    fake_dai.CameraBoardSocket.CAM_C = "CAM_C"

    # v2 pipeline: open() makes 6 create() calls (ColorCamera, XLinkOut(rgb),
    # MonoCamera x2, StereoDepth, XLinkOut(depth)); the default MagicMock per
    # call handles the set*/link wiring.
    fake_pipe = MagicMock()
    fake_dai.Pipeline.return_value = fake_pipe

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
