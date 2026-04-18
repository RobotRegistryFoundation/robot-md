from __future__ import annotations

from unittest.mock import MagicMock
import sys

from robot_md.autodetect import scan_system, DetectedCamera, DetectedCameraStream


def test_scan_has_cameras_field():
    scan = scan_system()
    assert hasattr(scan, "cameras")
    assert isinstance(scan.cameras, list)


def test_detected_camera_dataclass_shape():
    stream = DetectedCameraStream(
        name="rgb", intrinsic=None, baseline_m=None,
        derived_from=None, width=1280, height=720,
    )
    cam = DetectedCamera(
        driver_id="oak-d-1", protocol="depthai", model="OAK-D",
        streams=[stream], provenance="test",
    )
    assert cam.driver_id == "oak-d-1"
    assert cam.streams[0].name == "rgb"


def test_depthai_probe_reads_factory_cal(monkeypatch):
    """When depthai is importable and a device is present, factory cal is read."""
    fake_dai = MagicMock()
    fake_dai.CameraBoardSocket.CAM_A = "CAM_A"
    fake_dai.CameraBoardSocket.CAM_B = "CAM_B"
    fake_dai.CameraBoardSocket.CAM_C = "CAM_C"

    fake_feature_a = MagicMock()
    fake_feature_a.socket = "CAM_A"
    fake_feature_a.name = "rgb"
    fake_feature_b = MagicMock()
    fake_feature_b.socket = "CAM_B"
    fake_feature_b.name = "left"
    fake_feature_c = MagicMock()
    fake_feature_c.socket = "CAM_C"
    fake_feature_c.name = "right"

    fake_device = MagicMock()
    fake_device.getConnectedCameraFeatures.return_value = [fake_feature_a, fake_feature_b, fake_feature_c]
    fake_device.getDeviceName.return_value = "OAK-D"

    fake_calib = MagicMock()
    fake_calib.getCameraIntrinsics.return_value = [
        [860.2, 0.0, 640.0],
        [0.0, 860.2, 360.0],
        [0.0, 0.0, 1.0],
    ]
    fake_calib.getDistortionCoefficients.return_value = [0.0, 0.0, 0.0, 0.0, 0.0]
    fake_device.readCalibration.return_value = fake_calib
    fake_dai.Device.return_value.__enter__.return_value = fake_device
    fake_dai.Device.return_value.__exit__.return_value = False

    monkeypatch.setitem(sys.modules, "depthai", fake_dai)

    from robot_md.autodetect import probe_depthai_cameras

    cams = probe_depthai_cameras(default_width=1280, default_height=720)
    assert len(cams) == 1
    cam = cams[0]
    assert cam.protocol == "depthai"
    assert cam.model == "OAK-D"
    assert {s.name for s in cam.streams} == {"rgb", "left", "right"}
    rgb = next(s for s in cam.streams if s.name == "rgb")
    assert rgb.intrinsic["fx"] == 860.2
    assert rgb.intrinsic["distortion_model"] == "plumb_bob"
    assert rgb.intrinsic["distortion_coeffs"] == [0.0, 0.0, 0.0, 0.0, 0.0]


def test_depthai_probe_returns_empty_when_not_installed(monkeypatch):
    """With no depthai module, probe returns empty list rather than raising."""
    # Block depthai imports by setting sys.modules entry to None (ImportError on access)
    monkeypatch.setitem(sys.modules, "depthai", None)
    from robot_md.autodetect import probe_depthai_cameras

    assert probe_depthai_cameras() == []


def test_depthai_probe_returns_empty_when_calibration_fails(monkeypatch):
    """If reading calibration raises, the probe swallows the error and returns []."""
    fake_dai = MagicMock()
    fake_device = MagicMock()
    fake_device.getConnectedCameraFeatures.side_effect = RuntimeError("no device")
    fake_dai.Device.return_value.__enter__.return_value = fake_device
    fake_dai.Device.return_value.__exit__.return_value = False
    monkeypatch.setitem(sys.modules, "depthai", fake_dai)

    from robot_md.autodetect import probe_depthai_cameras

    assert probe_depthai_cameras() == []
