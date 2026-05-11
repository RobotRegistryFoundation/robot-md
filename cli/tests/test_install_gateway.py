from robot_md.install_gateway import render_systemd_unit


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
