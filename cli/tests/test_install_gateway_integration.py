import urllib.error
from unittest.mock import MagicMock, patch

from robot_md.install_gateway import (
    ENV_PATH,
    MANIFEST_PATH,
    install_gateway,
    render_default_bearers,
    render_env_file,
)


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
        if cmd[1:4] == ["python3", "-I", "-c"]:
            m.stdout = "created\n"  # a fresh host: the root helper creates each file
        elif cmd[1] == "cat":
            # What the install just wrote.
            m.stdout = (
                render_env_file(manifest_path=MANIFEST_PATH)
                if cmd[2] == ENV_PATH
                else render_default_bearers()
            )
        elif cmd[1:3] == ["systemctl", "is-enabled"]:
            m.stdout = "disabled\n"
        return m

    def gateway_answers_401(url, timeout):
        # The gateway's own answer on /v1/audit/last without a bearer.
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

    with (
        patch("robot_md.install_gateway.already_installed", return_value=False),
        patch("robot_md.install_gateway.subprocess.run", side_effect=fake_run),
        patch("os.path.exists", return_value=False),
        patch("urllib.request.urlopen", side_effect=gateway_answers_401),
    ):
        rc = install_gateway(manifest_path="/etc/robot-md-gateway/ROBOT.md", yes=True)

    assert rc == 0
    cmd_strs = [" ".join(c) if isinstance(c, list) else c for c in calls]
    assert any("useradd" in c for c in cmd_strs)
    assert any("pip" in c and "install" in c for c in cmd_strs)
    assert any("systemctl" in c and "daemon-reload" in c for c in cmd_strs)
    assert any("systemctl" in c and "enable" in c for c in cmd_strs)
