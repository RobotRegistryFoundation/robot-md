import importlib
import os
import stat
import subprocess
from importlib.metadata import version
from unittest.mock import patch

import pytest
import yaml
from packaging.version import Version

from robot_md.install_gateway import (
    BEARERS_PATH,
    CONFIG_DIR,
    ENV_PATH,
    HEALTH_URL,
    MANIFEST_PATH,
    _invoking_user,
    already_installed,
    bearer_problems,
    bearer_warnings,
    env_warnings,
    probe_gateway,
    render_default_bearers,
    render_env_file,
    render_systemd_unit,
    secure_existing_file,
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
    # The serial ports by class, not one node: ttyACM1, a CH340 or FTDI bridge
    # (ttyUSB*) and a node that appears after the start all reach the gateway.
    lines = unit.splitlines()
    assert "DeviceAllow=char-ttyACM rw" in lines
    assert "DeviceAllow=char-ttyUSB rw" in lines
    assert "DeviceAllow=/dev/ttyACM0 rw" not in lines
    # Stock Raspberry Pi OS: the ports are root:dialout 0660.
    assert "SupplementaryGroups=dialout" in lines


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
    (a 403 below it), and the driver checks the tier again."""
    env = render_env_file(manifest_path="/etc/robot-md-gateway/ROBOT.md")
    assert "arm.estop.clear" in _allowlist()
    [line] = [x for x in env.splitlines() if x.startswith("ROBOT_MD_TOOL_MIN_TIER=")]
    assert line == "ROBOT_MD_TOOL_MIN_TIER=arm.estop.clear:commission"


#: The two cross-checks below call functions robot-md-gateway added in 0.5.0a9.
#: cli/pyproject.toml still accepts older releases, which lack them, so the
#: checks skip there. From 0.5.0a9 on, a missing function FAILS: a rename in
#: the gateway must not turn a cross-check into a silent skip.
GATEWAY_CROSS_CHECKS_SINCE = "0.5.0a9"


def _gateway_module(name: str):
    installed = version("robot-md-gateway")
    if Version(installed) < Version(GATEWAY_CROSS_CHECKS_SINCE):
        pytest.skip(f"robot-md-gateway {installed} predates {GATEWAY_CROSS_CHECKS_SINCE}")
    return importlib.import_module(name)


def test_the_gateway_reads_the_clears_tier_floor_as_commission_only():
    """Cross-checked with the gateway's own parser of ROBOT_MD_TOOL_MIN_TIER:
    only the commission tier may invoke the clear."""
    parse = _gateway_module("robot_md_gateway.__main__")._build_tool_tier_requirements_from_env
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
    policy = _gateway_module("robot_md_gateway.cert.policy")

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


TOKEN_A, TOKEN_B = "A" * 43, "B" * 43


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # robot-md-gateway 0.5.0a9 (PyPI) stops with KeyError: 'tier' on this
        # one, and it is what the gateway's own create-bearers.sh writes.
        (f'bearers:\n  - token: "{TOKEN_A}"\n    role: supervisor\n', "has no valid tier"),
        # The next three load in 0.5.0a9 and are refused by robot-md-gateway#35.
        (
            f'bearers:\n  - token: "{TOKEN_A}"\n    tier: actuate\n    caller: agent\n'
            f'  - token: "{TOKEN_A}"\n    tier: read\n    role: supervisor\n',
            "entry 2 (no caller) uses the same token as entry 1 (agent)",
        ),
        (
            f'bearers:\n  - token: "{TOKEN_A}"\n    tier: actuate\n    role: supervisor\n',
            "is a supervisor with tier 'actuate'; a supervisor is read tier",
        ),
        (
            f'bearers:\n  - token: "{TOKEN_A}"\n    tier: read\n    role: admin\n',
            "has role 'admin'; the only role is 'supervisor'",
        ),
    ],
)
def test_bearer_problems_refuses_what_the_gateway_refuses_or_misreads(text, expected):
    """The review of #113, note 3: four files the installer passed and a
    gateway refuses or misreads."""
    problems = bearer_problems(text)
    assert any(expected in p for p in problems), problems
    assert not any(TOKEN_A in p for p in problems)


def test_bearer_problems_accepts_a_complete_file():
    text = (
        f'bearers:\n  - token: "{TOKEN_A}"\n    tier: actuate\n'
        f'  - token: "{TOKEN_B}"\n    tier: read\n    role: supervisor\n'
        f'  - token: "{"C" * 43}"\n    tier: commission\n'
    )
    assert bearer_problems(text) == []
    assert bearer_warnings(text) == []


def test_bearer_problems_never_repeats_a_token():
    token = "x" * 20
    problems = bearer_problems(f'bearers:\n  - token: "{token}"\n    tier: read\n')
    assert problems and not any(token in p for p in problems)


# --- what an upgrade's old files lack (review of #113, note 2) ---------------------


def test_bearer_warnings_name_a_missing_supervisor_and_commission_entry():
    warnings = bearer_warnings(f'bearers:\n  - token: "{TOKEN_A}"\n    tier: actuate\n')
    assert any("no `role: supervisor` entry" in w for w in warnings)
    assert any("no commission entry, so nothing can clear a stop" in w for w in warnings)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (
            "ROBOT_MD_TOOL_ALLOWLIST=move,home,read_state,perceive\n",
            "has no arm.estop",
        ),
        ("", "has no arm.estop"),
        (
            "ROBOT_MD_TOOL_ALLOWLIST=move,arm.estop,arm.estop.clear\n",
            "allowlists arm.estop.clear without ROBOT_MD_TOOL_MIN_TIER",
        ),
        (
            "ROBOT_MD_TOOL_ALLOWLIST=move,arm.estop,arm.estop.clear\n"
            "ROBOT_MD_TOOL_MIN_TIER=arm.estop.clear:actuate|commission\n",
            "allowlists arm.estop.clear without ROBOT_MD_TOOL_MIN_TIER",
        ),
        (
            "ROBOT_MD_PATH=/home/craig/ROBOT.md\nROBOT_MD_TOOL_ALLOWLIST=arm.estop\n",
            "ProtectHome=yes hides",
        ),
    ],
)
def test_env_warnings_name_what_an_old_gateway_env_lacks(env, expected):
    assert any(expected in w for w in env_warnings(env)), env_warnings(env)


def test_the_rendered_files_raise_no_warning_but_the_missing_commission_entry():
    assert env_warnings(render_env_file(manifest_path=MANIFEST_PATH)) == []
    [warning] = bearer_warnings(render_default_bearers())
    assert "no commission entry" in warning


# --- write_new_file and secure_existing_file (review of #113, notes 1 and 4) -------


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


def test_write_new_file_never_follows_a_symlink_at_the_name(tmp_path):
    target = tmp_path / "elsewhere"
    target.write_text("root's precious content\n")
    (tmp_path / "bearers.yaml").symlink_to(target)
    path = str(tmp_path / "bearers.yaml")
    assert write_new_file(path, "SECRET\n", mode="0600", owner=_me(), sudo=()) == "exists"
    assert target.read_text() == "root's precious content\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bearers.yaml", "elsewhere"]


def test_write_new_file_never_writes_into_a_directory_at_the_name(tmp_path):
    (tmp_path / "bearers.yaml").mkdir()
    path = str(tmp_path / "bearers.yaml")
    assert write_new_file(path, "SECRET\n", mode="0600", owner=_me(), sudo=()) == "exists"
    assert list((tmp_path / "bearers.yaml").iterdir()) == []


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


def _helper_functions() -> dict:
    """The root helper's functions, loaded in this process, for the tests
    that must watch it work."""
    from robot_md.install_gateway import _FILE_HELPER

    namespace: dict = {"__name__": "file_helper"}
    exec(compile(_FILE_HELPER, "file_helper", "exec"), namespace)
    return namespace


def test_the_root_helper_fsyncs_the_file_before_it_links_the_name(tmp_path, monkeypatch):
    """A power cut after the link must not leave an empty bearers.yaml, which
    the gateway would refuse to start on (the review of #113, note 4)."""
    helper = _helper_functions()
    events: list[str] = []
    real_fsync, real_link = os.fsync, os.link
    monkeypatch.setattr(os, "fsync", lambda fd: (events.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(os, "link", lambda *a, **k: (events.append("link"), real_link(*a, **k))[1])
    path = str(tmp_path / "bearers.yaml")
    assert helper["create"](path, _me(), 0o600, b"SECRET\n") == "created"
    assert events[:2] == ["fsync", "link"]
    assert events[-1] == "fsync"  # the directory, so the new name is durable too


def test_the_root_helper_runs_isolated_from_the_current_directory():
    """As root, a tempfile.py lying in the operator's cwd must not be imported."""
    from robot_md import install_gateway as ig

    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="created\n", stderr="")

    ig.write_new_file("/x/y", "z", mode="0600", owner="a:b", run=run)
    assert seen[0][:4] == ["sudo", "python3", "-I", "-c"]


def test_secure_existing_file_tightens_a_loose_file_and_names_what_it_was(tmp_path):
    path = tmp_path / "bearers.yaml"
    path.write_text("content\n")
    path.chmod(0o644)
    state, detail = secure_existing_file(str(path), owner=_me(), sudo=())
    assert state == "secured"
    assert detail == f"0644 {_me()}"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text() == "content\n"
    assert secure_existing_file(str(path), owner=_me(), sudo=()) == ("ok", "")


def test_secure_existing_file_refuses_a_symlink_and_a_directory(tmp_path):
    target = tmp_path / "elsewhere"
    target.write_text("x\n")
    target.chmod(0o644)
    (tmp_path / "link.yaml").symlink_to(target)
    (tmp_path / "dir.yaml").mkdir()
    assert secure_existing_file(str(tmp_path / "link.yaml"), owner=_me(), sudo=()) == (
        "failed",
        "it is a symbolic link, not a regular file",
    )
    assert secure_existing_file(str(tmp_path / "dir.yaml"), owner=_me(), sudo=()) == (
        "failed",
        "it is not a regular file",
    )
    assert stat.S_IMODE(target.stat().st_mode) == 0o644  # never followed


def test_secure_existing_file_never_takes_over_a_file_with_another_name(tmp_path):
    other = tmp_path / "elsewhere"
    other.write_text("x\n")
    other.chmod(0o644)
    os.link(other, tmp_path / "bearers.yaml")
    assert secure_existing_file(str(tmp_path / "bearers.yaml"), owner=_me(), sudo=()) == (
        "failed",
        "it has 2 hard links, so it is not changed",
    )
    assert stat.S_IMODE(other.stat().st_mode) == 0o644


# --- the health probe (review of #113, note 6) --------------------------------------


class _Answer:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen(*answers):
    """A urlopen that gives each answer in turn: an int is an HTTP status
    (urllib raises for 4xx and 5xx), an exception is raised."""
    import urllib.error

    queue = list(answers)

    def urlopen(url, timeout):
        answer = queue.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        if answer >= 400:
            raise urllib.error.HTTPError(url, answer, "status", {}, None)
        return _Answer(answer)

    return urlopen


def test_probe_gateway_takes_the_gateways_401_as_up():
    up, message = probe_gateway(urlopen=_urlopen(401), sleep=lambda s: None)
    assert up
    assert "HTTP 401" in message


def test_probe_gateway_waits_for_the_port_to_open():
    import urllib.error

    naps = []
    refused = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
    up, _ = probe_gateway(urlopen=_urlopen(refused, refused, 401), sleep=naps.append)
    assert up
    assert len(naps) == 2


@pytest.mark.parametrize("status", [200, 404, 500])
def test_probe_gateway_refuses_any_other_answer(status):
    up, message = probe_gateway(urlopen=_urlopen(status), sleep=lambda s: None)
    assert not up
    assert f"HTTP {status}" in message


def test_probe_gateway_gives_up_after_its_attempts():
    import urllib.error

    refused = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
    up, message = probe_gateway(attempts=3, urlopen=_urlopen(*[refused] * 3), sleep=lambda s: None)
    assert not up
    assert "after 3 tries" in message


def test_the_installed_gateway_answers_the_probe_route_with_401():
    """The route the probe reads, checked against the gateway robot-md
    installs alongside (0.5.0a9 from PyPI in CI). The installer used to GET
    "/", which no gateway serves: a working gateway answered 404."""
    from fastapi.testclient import TestClient

    receiver = importlib.import_module("robot_md_gateway.receiver")

    class _NoKeys:
        def resolve_public_key_pem(self, kid):
            return None

    client = TestClient(receiver.make_app(resolver=_NoKeys()))
    path = HEALTH_URL.split("8080", 1)[1]
    assert client.get(path).status_code == 401
    assert client.get("/").status_code == 404


# --- install_gateway against a fake host (review of #113, notes 1, 2, 4, 5) --------


class _FakeHost:
    """subprocess.run for install_gateway: records every command, keeps the
    files it creates in memory with their mode and owner, and runs nothing."""

    def __init__(self, existing: dict[str, str], *, mode="0600", owner=None, unit_state="disabled"):
        self.files = dict(existing)
        self.modes = {path: mode for path in existing}
        self.owners = {path: owner or "robot-md-gateway:robot-md-gateway" for path in existing}
        self.symlinks: set[str] = set()
        self.unit_state = unit_state
        self.commands: list[list[str]] = []

    def run(self, cmd, **kw):
        self.commands.append(list(cmd))
        args = [c for c in cmd if c != "sudo"]
        out, err, code = "", "", 0
        if args[:3] == ["python3", "-I", "-c"]:
            verb, path = args[4], args[5]
            if verb == "create":
                if path in self.files or path in self.symlinks:
                    out = "exists\n"
                else:
                    self.files[path] = kw.get("input", "")
                    self.modes[path], self.owners[path] = args[7], args[6]
                    out = "created\n"
            elif path in self.symlinks:
                err, code = "it is a symbolic link, not a regular file\n", 1
            elif int(self.modes[path], 8) & 0o077 or self.owners[path] != args[6]:
                out = f"secured {self.modes[path]} {self.owners[path]}\n"
                self.modes[path], self.owners[path] = "0600", args[6]
            else:
                out = "ok\n"
        elif args[:2] == ["systemctl", "is-enabled"]:
            out = self.unit_state + "\n"
        elif args[0] == "cat":
            code = 0 if args[1] in self.files else 1
            out = self.files.get(args[1], "")
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr=err)

    def ran(self, *words: str) -> list[list[str]]:
        return [c for c in self.commands if all(w in c for w in words)]


def _install(host: _FakeHost, manifest_path: str) -> int:
    from robot_md import install_gateway as ig

    with (
        patch.object(ig, "already_installed", return_value=False),
        patch.object(ig.subprocess, "run", side_effect=host.run),
        patch("urllib.request.urlopen", side_effect=_urlopen(401)),
    ):
        return ig.install_gateway(manifest_path=manifest_path, yes=True, add_user_to_group=False)


COMPLETE_BEARERS = (
    f'bearers:\n  - token: "{TOKEN_A}"\n    tier: actuate\n'
    f'  - token: "{TOKEN_B}"\n    tier: read\n    role: supervisor\n'
    f'  - token: "{"C" * 43}"\n    tier: commission\n'
)


def test_a_rerun_never_rewrites_the_content_of_bearers_or_gateway_env(tmp_path, capsys):
    """The review's Q7 (c): already_installed() is False whenever the unit is
    not active, and a rerun rewrote gateway.env and bearers.yaml."""
    env = render_env_file(manifest_path=MANIFEST_PATH) + "# edited by hand\n"
    host = _FakeHost({BEARERS_PATH: COMPLETE_BEARERS, ENV_PATH: env})
    assert _install(host, MANIFEST_PATH) == 0
    assert host.files == {BEARERS_PATH: COMPLETE_BEARERS, ENV_PATH: env}
    out = capsys.readouterr().out
    assert out.count("exists; its content, owner and mode are unchanged.") == 2
    assert "warning:" not in out


def test_an_old_install_with_loose_files_gets_them_tightened_and_says_so(tmp_path, capsys):
    """The review of #113, note 1: older installs made both files 0644, and
    the later `chown -R` put them in the operator's group."""
    env = render_env_file(manifest_path=MANIFEST_PATH)
    host = _FakeHost(
        {BEARERS_PATH: COMPLETE_BEARERS, ENV_PATH: env}, mode="0644", owner="root:root"
    )
    assert _install(host, MANIFEST_PATH) == 0
    out = capsys.readouterr().out
    for path in (BEARERS_PATH, ENV_PATH):
        assert (
            f"{path} exists; it was 0644 root:root, so it is now 0600 "
            "robot-md-gateway:robot-md-gateway. Its content is unchanged."
        ) in out
        assert (host.modes[path], host.owners[path]) == (
            "0600",
            "robot-md-gateway:robot-md-gateway",
        )
    assert host.files == {BEARERS_PATH: COMPLETE_BEARERS, ENV_PATH: env}


def test_the_config_directory_stays_roots_and_only_opt_is_chowned(tmp_path):
    host = _FakeHost({})
    assert _install(host, MANIFEST_PATH) == 0
    assert host.ran("chown", "root", CONFIG_DIR)
    assert host.ran("chmod", "go-w", CONFIG_DIR)
    [recursive] = host.ran("chown", "-R")
    assert recursive[-1] == "/opt/robot-md-gateway"
    assert CONFIG_DIR not in recursive


def test_a_fresh_install_creates_both_files_0600_through_the_root_helper(tmp_path):
    host = _FakeHost({})
    assert _install(host, MANIFEST_PATH) == 0
    assert bearer_problems(host.files[BEARERS_PATH]) == []
    assert "arm.estop" in host.files[ENV_PATH]
    for path in (BEARERS_PATH, ENV_PATH):
        assert (host.modes[path], host.owners[path]) == (
            "0600",
            "robot-md-gateway:robot-md-gateway",
        )
    # Never `tee <name>`, and never a separate command on a temporary name.
    assert not [c for c in host.commands if "tee" in c and c[-1] in (BEARERS_PATH, ENV_PATH)]
    assert not host.ran("mktemp") and not host.ran("ln")


def test_the_gateway_reads_the_etc_copy_of_any_manifest(tmp_path):
    """The review of #113, note 5: with `--manifest ~/ROBOT.md`, the gateway
    was pointed at a path the unit's ProtectHome=yes hides."""
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n")
    host = _FakeHost({})
    assert _install(host, str(manifest)) == 0
    assert f"ROBOT_MD_PATH={MANIFEST_PATH}\n" in host.files[ENV_PATH]
    assert host.ran("cp", str(manifest), MANIFEST_PATH)


def test_an_upgrade_warns_about_what_its_old_files_lack_and_still_installs(tmp_path, capsys):
    """The review of #113, note 2: an older install's files, kept as they are,
    left the upgrade silent."""
    old_bearers = f'bearers:\n  - token: "{TOKEN_A}"\n    tier: actuate\n    caller: agent\n'
    old_env = (
        "ROBOT_MD_PATH=/etc/robot-md-gateway/ROBOT.md\n"
        "ROBOT_MD_TOOL_ALLOWLIST=mcp__robot__execute_capability,move,home,read_state,perceive\n"
    )
    host = _FakeHost({BEARERS_PATH: old_bearers, ENV_PATH: old_env})
    assert _install(host, MANIFEST_PATH) == 0
    out = capsys.readouterr().out
    assert "warning: bearers.yaml has no `role: supervisor` entry" in out
    assert "warning: bearers.yaml has no commission entry, so nothing can clear a stop" in out
    assert "warning: gateway.env's ROBOT_MD_TOOL_ALLOWLIST has no arm.estop" in out
    assert host.ran("systemctl", "enable", "--now")
    for step in ("sudoedit", "sudo cat", "supervising person's device", "every 3 s", "clear"):
        assert step in out.split("next steps:", 1)[1]


def test_a_refused_bearers_file_disables_an_enabled_unit(tmp_path, capsys):
    """The review of #113: a unit enabled by an earlier run would load the
    refused file at the next boot."""
    host = _FakeHost({BEARERS_PATH: OLD_PLACEHOLDER_FILE}, unit_state="enabled")
    assert _install(host, MANIFEST_PATH) == 1
    out = capsys.readouterr().out
    assert "still has a placeholder token" in out
    assert "REPLACE-WITH-MINTED-TOKEN" not in out
    assert host.ran("systemctl", "disable", "robot-md-gateway")
    assert "disabled robot-md-gateway, so it does not load this file at the next boot." in out
    assert not host.ran("enable", "--now")
    assert host.files[BEARERS_PATH] == OLD_PLACEHOLDER_FILE


def test_an_existing_placeholder_bearers_file_stops_the_install_before_enabling(tmp_path, capsys):
    host = _FakeHost({BEARERS_PATH: OLD_PLACEHOLDER_FILE})
    assert _install(host, MANIFEST_PATH) == 1
    out = capsys.readouterr().out
    assert "still has a placeholder token" in out
    assert not host.ran("daemon-reload") and not host.ran("enable", "--now")
    assert not host.ran("systemctl", "disable", "robot-md-gateway")  # it was not enabled
    assert host.files[BEARERS_PATH] == OLD_PLACEHOLDER_FILE


def test_a_symlinked_bearers_file_is_refused(tmp_path, capsys):
    host = _FakeHost({ENV_PATH: render_env_file(manifest_path=MANIFEST_PATH)})
    host.symlinks.add(BEARERS_PATH)
    assert _install(host, MANIFEST_PATH) == 1
    assert "it is a symbolic link, not a regular file" in capsys.readouterr().out
    assert not host.ran("enable", "--now")


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
        "SupplementaryGroups=dialout",
        "DeviceAllow=char-ttyACM rw",
        "DeviceAllow=char-ttyUSB rw",
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
