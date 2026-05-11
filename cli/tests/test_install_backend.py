from robot_md.autodetect import Device
from robot_md.init_phases.install_backend import (
    PackageMatch,
    match_packages_for_devices,
)


def test_match_so_arm101_via_ch340_bus():
    """A Feetech servo bus hint should match so-arm101-actuator."""
    devices = [
        Device(role="serial-bus", driver_id="serial-ch340", protocol="serial",
               label="CH340", vid="1a86", pid="55d3", bus="usb"),
        Device(role="servo-bus", driver_id="feetech-bus-ttyACM0", protocol="feetech",
               label="6 servos", bus="probe", path="/dev/ttyACM0"),
    ]
    matches = match_packages_for_devices(devices)
    names = [m.package for m in matches]
    assert "so-arm101-actuator" in names


def test_match_oak_d_via_vidpid():
    """OAK-D (03e7:2485) should match oak-d-actuator."""
    devices = [
        Device(role="camera", driver_id="cam-oak-d", protocol="depthai",
               label="Luxonis OAK-D", vid="03e7", pid="2485", bus="usb"),
    ]
    matches = match_packages_for_devices(devices)
    names = [m.package for m in matches]
    assert "oak-d-actuator" in names


def test_match_dedups_by_package():
    """If two devices both indicate the same backend, return one match."""
    devices = [
        Device(role="serial-bus", driver_id="serial-ch340", protocol="serial",
               label="CH340", vid="1a86", pid="55d3", bus="usb"),
        Device(role="servo-bus", driver_id="feetech-bus-ttyACM0", protocol="feetech",
               label="6 servos", bus="probe", path="/dev/ttyACM0"),
        Device(role="serial-bus", driver_id="serial-ch340", protocol="serial",
               label="CH340 #2", vid="1a86", pid="55d3", bus="usb"),
    ]
    matches = match_packages_for_devices(devices)
    so_matches = [m for m in matches if m.package == "so-arm101-actuator"]
    assert len(so_matches) == 1
