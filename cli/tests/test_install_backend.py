from unittest.mock import patch

from robot_md.autodetect import Device
from robot_md.init_phases.install_backend import (
    InstallResult,
    PackageMatch,
    install_one,
    is_externally_managed_env,
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


def test_pep668_detected_when_marker_file_exists(tmp_path):
    """A Python install with an EXTERNALLY-MANAGED marker is detected."""
    marker = tmp_path / "EXTERNALLY-MANAGED"
    marker.write_text("")

    with patch("sysconfig.get_path", return_value=str(tmp_path)), \
         patch("sys.prefix", "/usr"), patch("sys.base_prefix", "/usr"):
        assert is_externally_managed_env() is True


def test_pep668_not_detected_in_venv():
    """A venv (sys.prefix != base_prefix) is never externally-managed."""
    with patch("sys.prefix", "/tmp/venv"), patch("sys.base_prefix", "/usr"):
        assert is_externally_managed_env() is False


def test_install_one_invokes_pip_with_break_system_packages_when_externally_managed():
    """When PEP 668 is in effect, pip install adds --break-system-packages."""
    captured_argv = []

    def fake_run(cmd, **kwargs):
        captured_argv.append(cmd)
        from subprocess import CompletedProcess
        return CompletedProcess(cmd, returncode=0,
                                stdout="Successfully installed so-arm101-actuator-0.2.1\n",
                                stderr="")

    with patch("robot_md.init_phases.install_backend.is_externally_managed_env",
               return_value=True), \
         patch("subprocess.run", side_effect=fake_run):
        result = install_one("so-arm101-actuator")

    assert result.ok
    assert any("--break-system-packages" in arg for arg in captured_argv[0])
    assert "so-arm101-actuator" in captured_argv[0]


def test_install_one_omits_break_system_packages_in_venv():
    """In a venv, pip install does NOT pass --break-system-packages."""
    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        from subprocess import CompletedProcess
        return CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    with patch("robot_md.init_phases.install_backend.is_externally_managed_env",
               return_value=False), \
         patch("subprocess.run", side_effect=fake_run):
        install_one("oak-d-actuator")

    assert not any("--break-system-packages" in arg for arg in captured[0])
