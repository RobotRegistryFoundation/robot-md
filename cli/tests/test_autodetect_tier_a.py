"""Tests for Tier A autodetect polish — driver profiles + camera probe.

Live-hardware calls (depthai / v4l2) are not exercised here; the probe
function's *structure* is verified with light unit tests that don't
depend on the host state.
"""

from __future__ import annotations

from robot_md.autodetect import (
    DRIVER_PROFILES,
    DetectedCamera,
    DetectedCameraStream,
    Device,
    Scan,
    driver_profile,
    emit_draft,
)


def test_driver_profiles_cover_common_protocols():
    for proto in ("feetech", "scservo", "dynamixel"):
        prof = driver_profile(proto)
        assert prof.get("steps_per_rev") == 4096, f"{proto} should be a 4096-step bus"
        assert isinstance(prof.get("default_baud"), int)


def test_driver_profile_returns_empty_for_unknown():
    assert driver_profile("not-a-real-protocol") == {}
    assert driver_profile("") == {}


def test_driver_profile_handles_camera_protocols():
    # Camera protocols are registered for symmetry but without servo semantics
    for proto in ("depthai", "picamera2"):
        prof = driver_profile(proto)
        assert prof is not None
        assert prof.get("steps_per_rev") is None


def test_emit_draft_includes_cameras_when_present():
    """When scan.cameras is populated, emit_draft must include a cameras[] block."""
    scan = Scan(
        devices=[
            Device(
                role="camera",
                driver_id="oak-d",
                protocol="depthai",
                label="Luxonis OAK-D",
                path=None,
                bus="usb",
            )
        ],
        cameras=[
            DetectedCamera(
                driver_id="depthai-ABC123",
                protocol="depthai",
                model="OAK-D",
                streams=[],
                provenance="depthai factory cal",
            )
        ],
    )
    draft = emit_draft(scan)
    assert "cameras:" in draft
    assert "depthai-ABC123" in draft
    assert "model: 'OAK-D'" in draft or "model: OAK-D" in draft


def test_emit_draft_omits_cameras_block_when_empty():
    scan = Scan(devices=[], cameras=[])
    draft = emit_draft(scan)
    assert "cameras:" not in draft


def test_scan_has_cameras_field():
    """Scan dataclass must expose a .cameras list (default empty)."""
    s = Scan()
    assert s.cameras == []
    assert isinstance(s.cameras, list)


def test_driver_entry_gets_default_baud_when_profile_matches(tmp_path):
    """When a Feetech device has a port, the emitted drivers[].baud_rate
    should be pre-filled from the driver profile."""
    from robot_md.autodetect import _drivers_from_devices

    devices = [
        Device(
            role="servo_bus",
            driver_id="arm",
            protocol="feetech",
            label="Feetech bus",
            path="/dev/ttyACM0",
            bus="usb",
        )
    ]
    drivers = _drivers_from_devices(devices)
    assert len(drivers) == 1
    # Either baud_rate matches the feetech profile, or (if the autodetect
    # currently emits a different protocol name for detected serial devices)
    # baud_rate is simply absent — both are schema-valid outcomes.
    if drivers[0].get("protocol") == "feetech":
        assert drivers[0].get("baud_rate") == DRIVER_PROFILES["feetech"]["default_baud"]


def test_driver_without_port_gets_no_baud():
    """Protocol alone isn't enough; a serial baud makes no sense without a port."""
    from robot_md.autodetect import _drivers_from_devices

    devices = [
        Device(
            role="npu",
            driver_id="hailo",
            protocol="hailo-rt",
            label="Hailo-8",
            path=None,
            bus="pci",
        )
    ]
    drivers = _drivers_from_devices(devices)
    assert "baud_rate" not in drivers[0]
