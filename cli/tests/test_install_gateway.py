from unittest.mock import patch

from robot_md.install_gateway import (
    _invoking_user,
    already_installed,
    render_default_bearers,
    render_env_file,
    render_systemd_unit,
)


def test_systemd_unit_content():
    """The rendered systemd unit matches Bob's known-good configuration."""
    unit = render_systemd_unit(manifest_path="/etc/robot-md-gateway/ROBOT.md")

    assert "[Unit]" in unit
    assert "Description=robot-md-gateway" in unit
    assert "After=network-online.target" in unit
    assert "User=robot-md-gateway" in unit
    assert "Group=robot-md-gateway" in unit
    assert "WorkingDirectory=/opt/robot-md-gateway" in unit
    assert "EnvironmentFile=/etc/robot-md-gateway/gateway.env" in unit
    assert (
        "ExecStart=/opt/robot-md-gateway/.venv/bin/robot-md-gateway serve "
        "--host 127.0.0.1 --port 8080 "
        "--bearers /etc/robot-md-gateway/bearers.yaml"
    ) in unit
    assert "DeviceAllow=/dev/ttyACM0 rw" in unit


def test_render_env_file_contains_required_keys():
    env = render_env_file(manifest_path="/etc/robot-md-gateway/ROBOT.md")
    assert "ROBOT_MD_PATH=/etc/robot-md-gateway/ROBOT.md" in env
    assert "ROBOT_MD_BEARERS_FILE=/etc/robot-md-gateway/bearers.yaml" in env
    assert "ROBOT_MD_LOG_LEVEL=INFO" in env
    assert "ROBOT_MD_REQUIRE_ENVELOPE_SIGNATURE=1" in env


def test_render_default_bearers_yaml_minimal():
    text = render_default_bearers()
    assert "bearers:" in text
    assert "REPLACE-WITH-MINTED-TOKEN" in text


def test_already_installed_detection():
    """venv binary present AND systemctl reports active → True."""
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("robot_md.install_gateway.subprocess.run") as run_mock,
    ):
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = "active\n"
        assert already_installed() is True


def test_not_installed_when_venv_missing():
    """venv binary missing → False without invoking systemctl."""
    with patch("pathlib.Path.exists", return_value=False):
        assert already_installed() is False


def test_invoking_user_returns_sudo_user_when_set():
    with patch.dict("os.environ", {"SUDO_USER": "alice"}, clear=False):
        assert _invoking_user() == "alice"


def test_invoking_user_returns_none_when_sudo_user_unset():
    with patch.dict("os.environ", {}, clear=True):
        assert _invoking_user() is None


def test_invoking_user_returns_none_when_sudo_user_is_root():
    # Direct root login (no SUDO_USER set, or SUDO_USER=root) → don't try to
    # add root to its own group; nothing meaningful to do.
    with patch.dict("os.environ", {"SUDO_USER": "root"}, clear=False):
        assert _invoking_user() is None
