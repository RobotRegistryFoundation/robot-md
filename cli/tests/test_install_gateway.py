from unittest.mock import patch

import pytest

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


def _allowlist() -> list[str]:
    env = render_env_file(manifest_path="/etc/robot-md-gateway/ROBOT.md")
    [line] = [x for x in env.splitlines() if x.startswith("ROBOT_MD_TOOL_ALLOWLIST=")]
    return line.split("=", 1)[1].split(",")


def test_render_env_file_allowlists_the_arm_stop():
    """The gateway's tool allowlist is default-deny: a stop missing from it is
    refused outright (403 `tool_allowlist`), and the gateway logs
    `allowlist_has_no_stop` at startup. `arm.estop` is the stop so-arm101-actuator
    declares in `stop_capabilities`, which is what the gateway routes as a stop."""
    assert "arm.estop" in _allowlist()


def test_render_env_file_allowlists_the_clear_at_the_commission_tier_only():
    """`arm.estop.clear` makes the arm movable again. Off the list, a latched arm
    could be unlatched only by restarting the gateway, with no record of who
    resumed it; on the list, it is held to the commission tier at the gateway
    (a signed 403 below it), and the driver checks the tier again."""
    env = render_env_file(manifest_path="/etc/robot-md-gateway/ROBOT.md")
    assert "arm.estop.clear" in _allowlist()
    [line] = [x for x in env.splitlines() if x.startswith("ROBOT_MD_TOOL_MIN_TIER=")]
    assert line == "ROBOT_MD_TOOL_MIN_TIER=arm.estop.clear:commission"


def test_the_gateway_reads_the_clears_tier_floor_as_commission_only():
    """Cross-checked with the gateway's own parser of ROBOT_MD_TOOL_MIN_TIER:
    only the commission tier may invoke the clear."""
    gw_main = pytest.importorskip("robot_md_gateway.__main__")
    parse = getattr(gw_main, "_build_tool_tier_requirements_from_env", None)
    if parse is None:
        pytest.skip("robot-md-gateway without ROBOT_MD_TOOL_MIN_TIER")
    env = render_env_file(manifest_path="/etc/robot-md-gateway/ROBOT.md")
    [line] = [x for x in env.splitlines() if x.startswith("ROBOT_MD_TOOL_MIN_TIER=")]
    with patch.dict("os.environ", {"ROBOT_MD_TOOL_MIN_TIER": line.split("=", 1)[1]}):
        requirements = parse()
    assert set(requirements["arm.estop.clear"]) == {"commission"}
    assert "arm.estop" not in requirements


def test_the_gateways_own_startup_check_finds_a_stop_in_the_rendered_allowlist():
    """Cross-checked with the gateway's own startup audit. The actuator below
    declares so-arm101-actuator's motion and stop tools (copied from its
    MOTION_CAPABILITIES and STOP_CAPABILITIES)."""
    policy = pytest.importorskip("robot_md_gateway.cert.policy")
    if not hasattr(policy, "audit_allowlist_for_stop"):
        pytest.skip("robot-md-gateway older than 0.5.0a9")

    class _SoArm101:
        motion_capabilities = frozenset(
            {"arm.home", "arm.reach", "arm.reach_point", "arm.move_to", "move", "home", "move_to"}
        )
        stop_capabilities = frozenset({"arm.estop"})

    allowlist = policy.ToolAllowlist(allowed_tools=tuple(_allowlist()))
    assert policy.audit_allowlist_for_stop(allowlist, [("so-arm101", _SoArm101())]) == []


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
