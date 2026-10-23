import os
import stat
import subprocess
from unittest.mock import patch

import pytest
import yaml

from robot_md.install_gateway import (
    BEARERS_PATH,
    ENV_PATH,
    _invoking_user,
    already_installed,
    bearer_problems,
    render_default_bearers,
    render_env_file,
    render_systemd_unit,
    write_new_file,
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


# --- bearers.yaml: real tokens, never a placeholder (review of #112, Q7 a) --------


def test_the_default_bearers_file_is_ready_to_use_and_holds_no_placeholder():
    text = render_default_bearers()
    assert "REPLACE-WITH" not in text
    assert bearer_problems(text) == []
    rows = yaml.safe_load(text)["bearers"]
    assert [(r["caller"], r["tier"], r.get("role")) for r in rows] == [
        ("actuate-default", "actuate", None),
        ("supervisor-default", "read", "supervisor"),
    ]
    assert all(len(r["token"]) >= 43 for r in rows)
    assert rows[0]["token"] != rows[1]["token"]
    # No commission entry: clearing a stop is added by hand, deliberately.
    assert "commission" not in {r["tier"] for r in rows}


def test_every_render_gets_its_own_tokens():
    first, second = (
        {r["token"] for r in yaml.safe_load(render_default_bearers())["bearers"]} for _ in range(2)
    )
    assert not first & second


def test_the_gateway_loads_the_default_bearers_file(tmp_path):
    """The old placeholder file raised KeyError: 'tier' in the gateway."""
    auth = pytest.importorskip("robot_md_gateway.auth")
    path = tmp_path / "bearers.yaml"
    path.write_text(render_default_bearers())
    store = auth.BearerStore.from_yaml(path)
    assert sorted(e.tier for e in store._by_token.values()) == ["actuate", "read"]


OLD_PLACEHOLDER_FILE = """\
bearers:
  - name: operator-default
    token: "REPLACE-WITH-MINTED-TOKEN"
    rrn: "RRN-XXXXXXXXXX"
"""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (OLD_PLACEHOLDER_FILE, "entry 1 (operator-default) still has a placeholder token"),
        (
            OLD_PLACEHOLDER_FILE.replace('rrn: "RRN-XXXXXXXXXX"', "tier: commission"),
            "entry 1 (operator-default) still has a placeholder token",
        ),
        (OLD_PLACEHOLDER_FILE, "entry 1 (operator-default) has no valid tier"),
        ('bearers:\n  - token: "<that token>"\n    tier: commission\n', "placeholder token"),
        ('bearers:\n  - token: "short"\n    tier: read\n    caller: c\n', "5-character token"),
        ("bearers:\n  - tier: read\n", "has no token"),
        ("bearers: []\n", "it has no bearer entries"),
        ("", "it has no bearer entries"),
        ("bearers: [unclosed\n", "it is not YAML"),
    ],
)
def test_bearer_problems_names_what_is_wrong(text, expected):
    problems = bearer_problems(text)
    assert any(expected in p for p in problems), problems


def test_bearer_problems_never_repeats_a_token():
    token = "x" * 20
    problems = bearer_problems(f'bearers:\n  - token: "{token}"\n    tier: read\n')
    assert problems and not any(token in p for p in problems)


# --- write_new_file: 0600, atomic, never clobbers (review of #112, Q7 b, c) ---------


def _me() -> str:
    import grp
    import pwd

    return f"{pwd.getpwuid(os.getuid()).pw_name}:{grp.getgrgid(os.getgid()).gr_name}"


def test_write_new_file_creates_it_with_its_mode_and_nothing_else(tmp_path):
    path = tmp_path / "bearers.yaml"
    assert write_new_file(str(path), "secret\n", mode="0600", owner=_me(), sudo=()) == "created"
    assert path.read_text() == "secret\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["bearers.yaml"]


def test_write_new_file_never_overwrites(tmp_path):
    path = tmp_path / "bearers.yaml"
    path.write_text("the operator's\n")
    path.chmod(0o640)
    assert write_new_file(str(path), "new\n", mode="0600", owner=_me(), sudo=()) == "exists"
    assert path.read_text() == "the operator's\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert [p.name for p in tmp_path.iterdir()] == ["bearers.yaml"]


def test_write_new_file_racing_itself_creates_exactly_one_file(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "bearers.yaml"
    with ThreadPoolExecutor(8) as pool:
        results = list(
            pool.map(
                lambda i: write_new_file(
                    str(path), f"run {i}\n", mode="0600", owner=_me(), sudo=()
                ),
                range(8),
            )
        )
    assert sorted(results) == ["created"] + ["exists"] * 7
    assert path.read_text().startswith("run ")
    assert [p.name for p in tmp_path.iterdir()] == ["bearers.yaml"]


def test_write_new_file_leaves_nothing_behind_when_it_fails(tmp_path):
    path = tmp_path / "bearers.yaml"
    result = write_new_file(str(path), "x\n", mode="0600", owner="no-such-user-xyz", sudo=())
    assert result == "failed"
    assert list(tmp_path.iterdir()) == []


# --- install_gateway never clobbers, and stops on a bad bearers.yaml ----------------


class _FakeHost:
    """subprocess.run for install_gateway: records every command, keeps the
    files it creates in memory, and runs nothing."""

    def __init__(self, existing: dict[str, str]):
        self.files = dict(existing)
        self.commands: list[list[str]] = []
        self.pending: dict[str, str] = {}

    def run(self, cmd, **kw):
        self.commands.append(list(cmd))
        args = [c for c in cmd if c != "sudo"]
        out, code = "", 0
        if args[:2] == ["test", "-e"]:
            code = 0 if args[2] in self.files else 1
        elif args[0] == "mktemp":
            out = args[1].replace("XXXXXXXX", f"tmp{len(self.commands)}")
        elif args[0] == "tee" and ".install." in args[1]:
            self.pending[args[1]] = kw.get("input", "")
        elif args[0] == "ln":
            if args[2] in self.files:
                code = 1
            else:
                self.files[args[2]] = self.pending.get(args[1], "")
        elif args[0] == "cat":
            code = 0 if args[1] in self.files else 1
            out = self.files.get(args[1], "")
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")


def _install(host: _FakeHost, tmp_path) -> int:
    from robot_md import install_gateway as ig

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with (
        patch.object(ig, "already_installed", return_value=False),
        patch.object(ig.subprocess, "run", side_effect=host.run),
        patch("urllib.request.urlopen", return_value=_Resp()),
    ):
        return ig.install_gateway(
            manifest_path=str(tmp_path / "ROBOT.md"), yes=True, add_user_to_group=False
        )


def test_a_rerun_never_overwrites_bearers_or_gateway_env(tmp_path):
    """The review's Q7 (c): already_installed() is False whenever the unit is
    not active, and a rerun rewrote gateway.env and bearers.yaml."""
    good = render_default_bearers()
    host = _FakeHost({BEARERS_PATH: good, ENV_PATH: "ROBOT_MD_TOOL_ALLOWLIST=mine\n"})
    assert _install(host, tmp_path) == 0
    assert host.files[BEARERS_PATH] == good
    assert host.files[ENV_PATH] == "ROBOT_MD_TOOL_ALLOWLIST=mine\n"
    assert not [c for c in host.commands if c[-1] in (BEARERS_PATH, ENV_PATH) and "tee" in c]
    assert not [c for c in host.commands if "ln" in c]


def test_a_fresh_install_creates_both_files_without_writing_to_their_names(tmp_path):
    host = _FakeHost({})
    assert _install(host, tmp_path) == 0
    assert bearer_problems(host.files[BEARERS_PATH]) == []
    assert "arm.estop" in host.files[ENV_PATH]
    # Never `tee <name>`: the content goes to a temporary file that already has
    # its owner and mode, and only then gets the name, by link(2).
    assert not [c for c in host.commands if "tee" in c and c[-1] in (BEARERS_PATH, ENV_PATH)]
    [link] = [c for c in host.commands if "ln" in c and c[-1] == BEARERS_PATH]
    tmp = link[-2]
    order = [c for c in host.commands if tmp in c]
    assert [c[1] for c in order] == ["chown", "chmod", "tee", "ln", "rm"]
    assert order[1][-2] == "0600"
    assert order[0][-2] == "robot-md-gateway:robot-md-gateway"


def test_an_existing_placeholder_bearers_file_stops_the_install_before_enabling(tmp_path, capsys):
    host = _FakeHost({BEARERS_PATH: OLD_PLACEHOLDER_FILE})
    assert _install(host, tmp_path) == 1
    out = capsys.readouterr().out
    assert "still has a placeholder token" in out
    assert "REPLACE-WITH-MINTED-TOKEN" not in out
    assert not [c for c in host.commands if "systemctl" in c]
    assert host.files[BEARERS_PATH] == OLD_PLACEHOLDER_FILE


# --- the unit is hardened (review of #112, note 5) ------------------------------------


def test_the_unit_fails_closed_without_the_bearer_file():
    assert f"AssertPathExists={BEARERS_PATH}" in render_systemd_unit()


@pytest.mark.parametrize(
    "directive",
    [
        "CapabilityBoundingSet=",
        "AmbientCapabilities=",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "RestrictNamespaces=yes",
        "SystemCallFilter=@system-service",
        "SystemCallFilter=~@privileged",
        "SystemCallErrorNumber=EPERM",
        "SystemCallArchitectures=native",
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
    ],
)
def test_the_unit_is_hardened(directive):
    assert directive in render_systemd_unit().splitlines()


def test_the_unit_scores_at_least_as_well_as_the_gateways_own_unit(tmp_path):
    """robot-md-gateway's dispatcher unit scores 4.9 with
    `systemd-analyze security --offline`; this unit scored 8.3."""
    import re
    import shutil

    if shutil.which("systemd-analyze") is None:
        pytest.skip("no systemd-analyze")
    unit = tmp_path / "robot-md-gateway.service"
    unit.write_text(render_systemd_unit())
    result = subprocess.run(
        ["systemd-analyze", "security", "--offline=true", "--no-pager", unit.name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"Overall exposure level for \S+: (\d+\.\d+)", result.stdout + result.stderr)
    if match is None:
        pytest.skip(f"systemd-analyze cannot score offline here: {result.stderr.strip()[:200]}")
    assert float(match.group(1)) <= 4.9
