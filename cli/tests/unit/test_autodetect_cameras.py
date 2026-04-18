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


def test_v4l2_probe_emits_null_intrinsic(monkeypatch, tmp_path):
    """v4l2 enumeration emits cameras with null intrinsic + provenance."""
    fake_dev = tmp_path / "video0"
    fake_dev.touch()
    monkeypatch.setattr("robot_md.autodetect._v4l2_list_devices", lambda: [str(fake_dev)])
    monkeypatch.setattr(
        "robot_md.autodetect._v4l2_device_capabilities",
        lambda p: {"model": "USB2 Camera", "width": 640, "height": 480},
    )
    from robot_md.autodetect import probe_v4l2_cameras

    cams = probe_v4l2_cameras()
    assert len(cams) == 1
    assert cams[0].protocol == "v4l2"
    assert cams[0].streams[0].intrinsic is None
    assert "no cal" in cams[0].provenance


def test_realsense_probe_returns_empty_when_not_installed(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyrealsense2", None)
    from robot_md.autodetect import probe_realsense_cameras

    assert probe_realsense_cameras() == []


def test_scan_system_composes_cameras(monkeypatch):
    """scan_system() composes all three probes into Scan.cameras."""
    from robot_md import autodetect
    from robot_md.autodetect import DetectedCamera, DetectedCameraStream

    monkeypatch.setattr(autodetect, "probe_depthai_cameras", lambda: [
        DetectedCamera(driver_id="oak-d-1", protocol="depthai", model="OAK-D",
                       streams=[], provenance="depthai factory cal")
    ])
    monkeypatch.setattr(autodetect, "probe_realsense_cameras", lambda: [])
    monkeypatch.setattr(autodetect, "probe_v4l2_cameras", lambda: [
        DetectedCamera(driver_id="usb-camera-video0", protocol="v4l2", model="USB",
                       streams=[], provenance="v4l2 enum / no cal")
    ])
    scan = autodetect.scan_system()
    protos = {c.protocol for c in scan.cameras}
    assert "depthai" in protos
    assert "v4l2" in protos


def test_scan_cameras_is_typed_list_of_DetectedCamera():
    """After T06, Scan.cameras contains DetectedCamera instances, not dicts."""
    from robot_md.autodetect import scan_system, DetectedCamera
    scan = scan_system()
    assert all(isinstance(c, DetectedCamera) for c in scan.cameras)
