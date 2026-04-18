from __future__ import annotations

from dataclasses import dataclass, field

from robot_md.autodetect import DetectedCamera, DetectedCameraStream
from robot_md.init import load_presets, merge_preset_into_draft


@dataclass
class _FakeScan:
    devices: list = field(default_factory=list)
    cameras: list = field(default_factory=list)


def test_merge_adds_detected_camera_to_drivers_and_cameras():
    scan = _FakeScan(cameras=[
        DetectedCamera(
            driver_id="oak-d-1",
            protocol="depthai",
            model="OAK-D",
            streams=[
                DetectedCameraStream(
                    name="rgb",
                    intrinsic={"fx": 860.2, "fy": 860.2, "cx": 640.0, "cy": 360.0,
                               "width": 1280, "height": 720,
                               "distortion_model": "plumb_bob",
                               "distortion_coeffs": [0.0] * 5},
                    baseline_m=None, derived_from=None,
                    width=1280, height=720,
                ),
            ],
            provenance="depthai factory cal",
        )
    ])

    presets = load_presets()
    preset = next(p for p in presets if p.name == "so_arm101")
    fm = merge_preset_into_draft(preset, "bob", scan)

    cam_driver = next((d for d in fm["drivers"] if d.get("id") == "oak-d-1"), None)
    assert cam_driver is not None, f"oak-d-1 driver not injected: {fm['drivers']}"
    assert cam_driver["streams"]["rgb"]["intrinsic"]["fx"] == 860.2
    assert cam_driver["protocol"] == "depthai"

    cams = (fm.get("physics", {}).get("solver", {}).get("cameras")) or []
    assert any(c["driver_id"] == "oak-d-1" for c in cams), f"cameras[] missing entry: {cams}"
    injected = next(c for c in cams if c["driver_id"] == "oak-d-1")
    assert injected["primary_stream"] == "rgb"
    assert injected["mount"] == "world"
    assert injected["extrinsic"] is None


def test_merge_without_detected_cameras_is_a_noop():
    scan = _FakeScan(cameras=[])
    presets = load_presets()
    preset = next(p for p in presets if p.name == "so_arm101")
    fm = merge_preset_into_draft(preset, "bob", scan)
    # so_arm101 preset has no cameras declared — none should be injected
    cams = (fm.get("physics", {}).get("solver", {}).get("cameras")) or []
    assert cams == [] or not any(c.get("protocol") == "depthai" for c in cams)


def test_merge_preserves_preset_cameras_when_detected_adds_more():
    """A preset that already ships cameras (like aloha2) keeps them and adds detected."""
    scan = _FakeScan(cameras=[
        DetectedCamera(
            driver_id="extra-cam",
            protocol="depthai",
            model="OAK-D",
            streams=[DetectedCameraStream(
                name="rgb", intrinsic=None, baseline_m=None, derived_from=None,
                width=1280, height=720,
            )],
            provenance="depthai factory cal",
        )
    ])
    presets = load_presets()
    preset = next(p for p in presets if p.name == "aloha2")
    fm = merge_preset_into_draft(preset, "alo", scan)
    cams = (fm.get("physics", {}).get("solver", {}).get("cameras")) or []
    # Original 4 preset cameras + 1 injected = 5
    assert len(cams) == 5
    assert any(c["driver_id"] == "extra-cam" for c in cams)
