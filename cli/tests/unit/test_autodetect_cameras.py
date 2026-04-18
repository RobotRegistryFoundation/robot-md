from __future__ import annotations

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
