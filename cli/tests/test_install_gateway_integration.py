from unittest.mock import MagicMock, patch

from robot_md.install_gateway import install_gateway


def test_install_gateway_skips_when_already_installed(capsys):
    """already_installed → print status, return 0, no side effects."""
    with (
        patch("robot_md.install_gateway.already_installed", return_value=True),
        patch("robot_md.install_gateway.subprocess.run") as run_mock,
    ):
        rc = install_gateway(manifest_path="/etc/robot-md-gateway/ROBOT.md", yes=True)

    assert rc == 0
    out = capsys.readouterr().out
    assert "already installed" in out.lower()
    run_mock.assert_not_called()


def test_install_gateway_runs_full_sequence_when_fresh():
    """Fresh install runs: useradd → pip install → write config → systemd."""
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        return m

    with (
        patch("robot_md.install_gateway.already_installed", return_value=False),
        patch("robot_md.install_gateway.subprocess.run", side_effect=fake_run),
        patch("os.path.exists", return_value=False),
        patch("urllib.request.urlopen") as urlopen_mock,
    ):
        urlopen_mock.return_value.__enter__.return_value.status = 200
        rc = install_gateway(manifest_path="/etc/robot-md-gateway/ROBOT.md", yes=True)

    assert rc == 0
    cmd_strs = [" ".join(c) if isinstance(c, list) else c for c in calls]
    assert any("useradd" in c for c in cmd_strs)
    assert any("pip" in c and "install" in c for c in cmd_strs)
    assert any("systemctl" in c and "daemon-reload" in c for c in cmd_strs)
    assert any("systemctl" in c and "enable" in c for c in cmd_strs)
