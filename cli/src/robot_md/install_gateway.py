"""robot-md install-gateway subcommand.

Scaffolds the Layer 3 enforcement gateway on a fresh host:
  - Creates `robot-md-gateway` system user
  - pip-installs `robot-md-gateway` into /opt/robot-md-gateway/.venv/
  - Writes /etc/robot-md-gateway/{gateway.env, bearers.yaml, ROBOT.md}
  - Installs + enables a systemd unit
  - Verifies the gateway answers on 127.0.0.1:8080

Idempotent: detects an already-installed gateway and prints status without
clobbering. It never rewrites the content of bearers.yaml or gateway.env, even
when it runs again on a gateway that is installed but not active. It does
tighten their owner and mode, and says so when it does. Requires sudo for the
actual filesystem + systemd writes.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import yaml

GATEWAY_USER = "robot-md-gateway"
SERVICE_OWNER = f"{GATEWAY_USER}:{GATEWAY_USER}"
CONFIG_DIR = "/etc/robot-md-gateway"
BEARERS_PATH = f"{CONFIG_DIR}/bearers.yaml"
ENV_PATH = f"{CONFIG_DIR}/gateway.env"
#: Where the gateway reads its manifest, whatever `--manifest` named: the unit
#: runs with ProtectHome=yes, so a manifest under /home is invisible to it.
MANIFEST_PATH = f"{CONFIG_DIR}/ROBOT.md"
#: The gateway's own route, answered 401 without a bearer by every release that
#: has it (0.5.0a9, and robot-md-gateway#35): an answer only the gateway gives.
HEALTH_URL = "http://127.0.0.1:8080/v1/audit/last"

#: Shortest token `install-gateway` accepts in bearers.yaml.
#: `secrets.token_urlsafe(32)`, which it generates, gives 43 characters.
MIN_TOKEN_CHARS = 32

_EXEC_START = (
    "/opt/robot-md-gateway/.venv/bin/robot-md-gateway serve "
    "--host 127.0.0.1 --port 8080 "
    "--bearers /etc/robot-md-gateway/bearers.yaml"
)


SYSTEMD_UNIT_TEMPLATE = f"""\
[Unit]
Description=robot-md-gateway — enforcement gateway between agent intent and actuators
After=network-online.target
Wants=network-online.target
# Fail closed: no bearer file, no gateway, refused once and loudly.
AssertPathExists={BEARERS_PATH}

[Service]
User=robot-md-gateway
Group=robot-md-gateway
# On a stock Raspberry Pi OS the serial ports are root:dialout 0660, and nothing
# here installs a udev rule that hands them to robot-md-gateway.
SupplementaryGroups=dialout
WorkingDirectory=/opt/robot-md-gateway
EnvironmentFile={ENV_PATH}
ExecStart={_EXEC_START}
Restart=on-failure
RestartSec=3s

NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=no
# The arm's serial adapter, whatever it enumerates as: cdc_acm (ttyACM*) or a
# USB-serial bridge (ttyUSB*), including a node that appears after the start.
DeviceAllow=char-ttyACM rw
DeviceAllow=char-ttyUSB rw
# No capabilities, only the socket families an HTTP server and its key lookups
# use, no new namespaces, and the system calls of an ordinary service. A call
# outside that set fails with EPERM rather than killing the process.
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictNamespaces=yes
SystemCallFilter=@system-service
SystemCallFilter=~@privileged
SystemCallErrorNumber=EPERM
SystemCallArchitectures=native
LockPersonality=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectHostname=yes

[Install]
WantedBy=multi-user.target
"""


def render_systemd_unit(*, manifest_path: str = "/etc/robot-md-gateway/ROBOT.md") -> str:
    """Return the rendered systemd unit text. manifest_path informs the env
    file (separate write); the unit itself is invariant of manifest location."""
    return SYSTEMD_UNIT_TEMPLATE


def render_env_file(*, manifest_path: str) -> str:
    """Render the contents of /etc/robot-md-gateway/gateway.env.

    The gateway's tool allowlist is default-deny, so it carries the arm's stop
    (`arm.estop`, the tool so-arm101-actuator declares in `stop_capabilities`)
    next to the motion it allows. A stop missing from it is refused by the
    gateway, and the gateway logs `allowlist_has_no_stop` at startup.

    It carries the arm's clear too (`arm.estop.clear`), and only at the
    commission tier: `ROBOT_MD_TOOL_MIN_TIER` makes the gateway refuse a lower
    tier with a 403 before the driver checks again. The 403 is signed only
    when the gateway has an attestation key, which install-gateway does not
    configure. Without the clear on the list, a latched arm could be unlatched
    only by restarting the gateway, which also throws away the in-memory latch
    with no record of who resumed it. The gateway refuses the clear while it is
    itself tripped, because the clear is not a stop, so the order stays: the
    gateway's clear (`POST /v1/safety/clear`) first, then the arm's.
    """
    return f"""\
ROBOT_MD_PATH={manifest_path}
ROBOT_MD_BEARERS_FILE=/etc/robot-md-gateway/bearers.yaml
ROBOT_MD_LOG_LEVEL=INFO
# arm.estop is the arm's stop: keep it on this list, the gateway refuses any tool that is not.
# arm.estop.clear unlatches the arm: commission tier only (next line).
ROBOT_MD_TOOL_ALLOWLIST=mcp__robot__execute_capability,mcp__robot__render,mcp__robot__validate,move,home,read_state,perceive,arm.estop,arm.estop.clear
ROBOT_MD_TOOL_MIN_TIER=arm.estop.clear:commission
ROBOT_MD_REQUIRE_ENVELOPE_SIGNATURE=1
"""


def new_token() -> str:
    """A bearer token: 32 random bytes, URL-safe base64 (43 characters)."""
    return secrets.token_urlsafe(32)


def render_default_bearers(*, token: Callable[[], str] = new_token) -> str:
    """Render a new bearers.yaml, ready to use, with freshly generated tokens:
    an actuate-tier one for the agent's client and a supervisor one for the
    device that sends the gateway's heartbeats. It holds no commission token:
    clearing a stop is a deliberate act, so the operator adds that entry by
    hand, and the file shows how.

    It used to hold the public string `REPLACE-WITH-MINTED-TOKEN` with no tier,
    which the gateway could not load (`KeyError: 'tier'`); an operator who
    added a tier by hand and kept the placeholder had a working credential
    anyone could read in this source file.
    """
    return f"""\
# bearers.yaml: the credentials robot-md-gateway accepts, one entry per client,
# so each receipt names the credential that acted (caller). Generated by
# `robot-md install-gateway`. Never commit it. tier: read | actuate | commission.
bearers:
  # The agent's client. It can move the robot; it cannot clear a stop.
  - token: "{token()}"
    tier: actuate
    caller: actuate-default
  # The heartbeat sender: the supervising person's device, never the agent's
  # host and never the robot. It can stop the robot and read; nothing else.
  # A gateway without supervisor roles reads it as a read-tier credential.
  - token: "{token()}"
    tier: read
    role: supervisor
    caller: supervisor-default
  # Clearing a stop (POST /v1/safety/clear, then arm.estop.clear) needs a
  # commission entry. Add the operator's by hand, with a token of its own:
  #   python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
  # - token: "<that token>"
  #   tier: commission
  #   caller: <the operator>
"""


_TIERS = ("read", "actuate", "commission")
_SUPERVISOR = "supervisor"


def _bearer_rows(text: str) -> tuple[list, str | None]:
    """(the entries of a bearers.yaml, None), or ([], the YAML error's type).
    Both shapes the gateway reads: a top-level list, or a mapping with
    `bearers:`."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [], type(exc).__name__
    rows = data.get("bearers") if isinstance(data, dict) else data
    return (rows if isinstance(rows, list) else []), None


def bearer_problems(text: str) -> list[str]:
    """What is wrong with a bearers.yaml, as sentences an operator can act on.
    Empty when nothing is. Tokens are never repeated back.

    Refused, so that the installer never enables a gateway on a file that
    robot-md-gateway 0.5.0a9 (on PyPI) or robot-md-gateway#35 would refuse or
    misread:
    - a file that is not YAML, or has no entries; an entry that is not a mapping;
    - an entry with no token, or a placeholder token (anything with
      `REPLACE-WITH` in it, or starting with "<"), or one shorter than
      MIN_TOKEN_CHARS;
    - an entry with no tier, a supervisor's included (0.5.0a9 stops with
      `KeyError: 'tier'` on one), or a tier other than read, actuate, commission;
    - a role other than `supervisor`, or a supervisor whose tier is not read;
    - a token listed in more than one entry.
    """
    rows, error = _bearer_rows(text)
    if error is not None:
        return [f"it is not YAML ({error})"]
    if not rows:
        return ["it has no bearer entries"]
    problems = []
    seen: dict[str, str] = {}
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            problems.append(f"entry {i} is not a mapping")
            continue
        who = f"entry {i} ({row.get('caller') or row.get('name') or 'no caller'})"
        token = row.get("token")
        if not isinstance(token, str) or not token.strip():
            problems.append(f"{who} has no token")
        elif "REPLACE-WITH" in token.upper() or token.startswith("<"):
            problems.append(f"{who} still has a placeholder token")
        elif len(token) < MIN_TOKEN_CHARS:
            problems.append(
                f"{who} has a {len(token)}-character token; use at least {MIN_TOKEN_CHARS}"
            )
        if isinstance(token, str) and token:
            if token in seen:
                problems.append(f"{who} uses the same token as {seen[token]}")
            else:
                seen[token] = who
        tier, role = row.get("tier"), row.get("role")
        if tier not in _TIERS:
            problems.append(f"{who} has no valid tier (read, actuate or commission)")
        if role is not None and role != _SUPERVISOR:
            problems.append(f"{who} has role {role!r}; the only role is {_SUPERVISOR!r}")
        elif role == _SUPERVISOR and tier in _TIERS and tier != "read":
            problems.append(f"{who} is a supervisor with tier {tier!r}; a supervisor is read tier")
    return problems


def bearer_warnings(text: str) -> list[str]:
    """What a bearers.yaml that loads still lacks, for an operator to add."""
    rows = [r for r in _bearer_rows(text)[0] if isinstance(r, dict)]
    warnings = []
    if not any(r.get("role") == _SUPERVISOR for r in rows):
        warnings.append(
            "bearers.yaml has no `role: supervisor` entry, so no heartbeat can be sent; "
            "a robot-md-gateway that boots held (robot-md-gateway#35 and later) never arms"
        )
    if not any(r.get("tier") == "commission" for r in rows):
        warnings.append("bearers.yaml has no commission entry, so nothing can clear a stop")
    return warnings


def _env_values(text: str) -> dict[str, str]:
    """KEY=VALUE lines of an EnvironmentFile, comments skipped, quotes removed."""
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _tier_floors(raw: str) -> dict[str, set[str]]:
    """ROBOT_MD_TOOL_MIN_TIER, read the way the gateway reads it."""
    floors: dict[str, set[str]] = {}
    for pair in raw.split(","):
        tool, sep, tiers = pair.strip().partition(":")
        allowed = {t.strip() for t in tiers.split("|") if t.strip()}
        if sep and tool.strip() and allowed:
            floors[tool.strip()] = allowed
    return floors


def env_warnings(text: str) -> list[str]:
    """What an existing gateway.env lacks that this installer would now write."""
    values = _env_values(text)
    allowed = {t.strip() for t in values.get("ROBOT_MD_TOOL_ALLOWLIST", "").split(",") if t.strip()}
    warnings = []
    if "arm.estop" not in allowed:
        warnings.append(
            "gateway.env's ROBOT_MD_TOOL_ALLOWLIST has no arm.estop, so the gateway refuses "
            "the arm's stop (403 tool_allowlist); add it"
        )
    floors = _tier_floors(values.get("ROBOT_MD_TOOL_MIN_TIER", ""))
    if "arm.estop.clear" in allowed and floors.get("arm.estop.clear") != {"commission"}:
        warnings.append(
            "gateway.env allowlists arm.estop.clear without "
            "ROBOT_MD_TOOL_MIN_TIER=arm.estop.clear:commission, so the gateway does not hold "
            "the arm's unlatch to the commission tier itself"
        )
    manifest = values.get("ROBOT_MD_PATH", "")
    if manifest.startswith(("/home/", "/root/")):
        warnings.append(
            f"gateway.env's ROBOT_MD_PATH is {manifest}, which the unit's ProtectHome=yes hides "
            f"from the gateway; point it at {MANIFEST_PATH}"
        )
    return warnings


#: Runs as root (`sudo python3 -c _FILE_HELPER ...`). One process does all of a
#: file's work through one descriptor, in the root-owned config directory, so
#: nothing between two sudo calls can swap a name.
#: - `create PATH OWNER MODE`, content on stdin: prints "created", or "exists"
#:   when anything already has the name (never followed, never replaced).
#: - `secure PATH OWNER`: prints "ok", or "secured MODE OWNER:GROUP" naming what
#:   it was, after setting it to OWNER and 0600 when it was readable by group or
#:   others or owned by someone else. Refuses a name that is not a regular file,
#:   and a file with another name (a hard link), which it would take over too.
#: Anything else exits 1 with the reason on stderr.
_FILE_HELPER = r"""
import errno, grp, os, pwd, stat, sys, tempfile


def _ids(owner):
    user, _, group = owner.partition(":")
    return pwd.getpwnam(user).pw_uid, grp.getgrnam(group or user).gr_gid


def _name(lookup, number):
    try:
        return lookup(number)[0]
    except KeyError:
        return str(number)


def create(path, owner, mode, data):
    uid, gid = _ids(owner)
    if os.path.lexists(path):
        return "exists"
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".install.")
    try:
        os.fchown(fd, uid, gid)
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
        try:
            os.link(tmp, path)
        except FileExistsError:
            return "exists"
        dfd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        return "created"
    finally:
        os.close(fd)
        os.unlink(tmp)


def secure(path, owner):
    uid, gid = _ids(owner)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError("it is a symbolic link, not a regular file") from None
        raise
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("it is not a regular file")
        if st.st_uid == uid and st.st_gid == gid and not st.st_mode & 0o077:
            return "ok"
        if st.st_nlink != 1:
            raise ValueError("it has %d hard links, so it is not changed" % st.st_nlink)
        old = "%04o %s:%s" % (stat.S_IMODE(st.st_mode), _name(pwd.getpwuid, st.st_uid),
                              _name(grp.getgrgid, st.st_gid))
        os.fchown(fd, uid, gid)
        os.fchmod(fd, 0o600)
        os.fsync(fd)
        return "secured " + old
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        if sys.argv[1] == "create":
            print(create(sys.argv[2], sys.argv[3], int(sys.argv[4], 8), sys.stdin.buffer.read()))
        elif sys.argv[1] == "secure":
            print(secure(sys.argv[2], sys.argv[3]))
        else:
            raise ValueError("unknown command " + sys.argv[1])
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__ + ": " + str(exc)
        print(reason, file=sys.stderr)
        sys.exit(1)
"""


def _file_helper(
    args: list[str],
    *,
    sudo: list[str] | tuple[str, ...],
    run: Callable[..., subprocess.CompletedProcess] | None,
    content: str = "",
) -> subprocess.CompletedProcess:
    # -I: as root, never import from the operator's current directory or honour
    # PYTHON* variables; a tempfile.py lying in the cwd would otherwise run.
    return (run or subprocess.run)(
        [*sudo, "python3", "-I", "-c", _FILE_HELPER, *args],
        input=content,
        capture_output=True,
        text=True,
    )


def write_new_file(
    path: str,
    content: str,
    *,
    mode: str,
    owner: str,
    sudo: list[str] | tuple[str, ...] = ("sudo",),
    run: Callable[..., subprocess.CompletedProcess] | None = None,
) -> str:
    """Create `path` with `content`, or leave an existing name alone.

    Returns "created", "exists", or "failed". One root process (`_FILE_HELPER`)
    creates a temporary file in the same directory with O_EXCL (0600), sets its
    owner and mode through the descriptor, writes the content, fsyncs it, and
    only then gives it the name with link(2), which never follows or replaces
    an existing name, a symlink or a directory included. The temporary file is
    removed whatever happens. With the directory root's (install_gateway sees
    to that), no other account can swap a name in between, and a run racing
    another cannot replace the other's file.
    """
    done = _file_helper(["create", path, owner, mode], sudo=sudo, run=run, content=content)
    result = (done.stdout or "").strip()
    return result if done.returncode == 0 and result in ("created", "exists") else "failed"


def secure_existing_file(
    path: str,
    *,
    owner: str,
    sudo: list[str] | tuple[str, ...] = ("sudo",),
    run: Callable[..., subprocess.CompletedProcess] | None = None,
) -> tuple[str, str]:
    """Make an existing file `owner` and 0600 if it is readable by group or
    others, or owned by anyone else. Its content is not touched.

    Returns ("ok", ""), ("secured", "<old mode> <old owner:group>") or
    ("failed", why): a name that is not a regular file, a symlink included, is
    refused rather than followed, and so is a file with another hard link.
    """
    done = _file_helper(["secure", path, owner], sudo=sudo, run=run)
    result = (done.stdout or "").strip()
    if done.returncode == 0 and result == "ok":
        return "ok", ""
    if done.returncode == 0 and result.startswith("secured "):
        return "secured", result.removeprefix("secured ")
    return "failed", (done.stderr or "").strip() or "the check could not run"


def probe_gateway(
    url: str = HEALTH_URL,
    *,
    attempts: int = 15,
    delay_s: float = 1.0,
    urlopen: Callable | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[bool, str]:
    """Is the gateway itself answering? GET HEALTH_URL with no bearer and expect
    the gateway's 401. It used to GET "/", which no gateway serves: a working
    gateway answered 404, and the installer reported a failure. Retries while
    the port is not open yet, since the service takes a moment to start."""
    import urllib.error
    import urllib.request

    urlopen = urlopen or urllib.request.urlopen
    last = ""
    for _ in range(attempts):
        try:
            with urlopen(url, timeout=5) as resp:
                status = resp.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        except (urllib.error.URLError, OSError) as exc:
            last = str(getattr(exc, "reason", exc))
            sleep(delay_s)
            continue
        if status == 401:
            return True, f"gateway answered {url} with HTTP 401 (no bearer sent), as it should"
        return False, f"{url} answered HTTP {status}, not the gateway's 401"
    return False, f"no answer from {url} after {attempts} tries ({last})"


def already_installed() -> bool:
    """True when /opt/robot-md-gateway/.venv has the gateway binary AND
    systemd reports the unit active. Either alone returns False — we want
    both for confidence."""
    venv_binary = Path("/opt/robot-md-gateway/.venv/bin/robot-md-gateway")
    if not venv_binary.exists():
        return False
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "robot-md-gateway"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "active"


def _invoking_user() -> str | None:
    """Return the user who invoked sudo, or None when running unprivileged
    or directly as root with no SUDO_USER. Used to grant the operator access
    to the `robot-md-gateway` group during install so that `robot-md init`
    can probe /dev/ttyACM* (which the udev rule hardens to gateway-only)."""
    user = os.environ.get("SUDO_USER")
    if user and user != "root":
        return user
    return None


#: Printed after an install, as robot-md-gateway's own systemd/install.sh does.
NEXT_STEPS = f"""\
next steps:
  1. add a commission entry for the operator: sudoedit {BEARERS_PATH}
     (the file shows how). Without one, nothing can clear a stop.
  2. read the tokens with: sudo cat {BEARERS_PATH}
  3. give the actuate token to the agent's client, and the supervisor token to
     the supervising person's device: never the agent's host, never the robot.
  4. from that device, POST /v1/safety/heartbeat at least every 3 s.
  5. then, as the operator, POST /v1/safety/clear with the commission token.
     A gateway that has these routes (robot-md-gateway#35 and later) starts
     held and moves nothing until then; 0.5.0a9 has neither route."""


def _disable_unit_if_enabled(sudo: list[str]) -> None:
    """A refused bearers.yaml must not be loaded at the next boot either."""
    state = subprocess.run(
        [*sudo, "systemctl", "is-enabled", "robot-md-gateway"], capture_output=True, text=True
    )
    if (state.stdout or "").strip().startswith("enabled"):
        done = subprocess.run([*sudo, "systemctl", "disable", "robot-md-gateway"])
        if done.returncode == 0:
            print("disabled robot-md-gateway, so it does not load this file at the next boot.")
        else:
            print("warning: could not disable robot-md-gateway; it would load this file at boot.")


def install_gateway(
    *, manifest_path: str, yes: bool = False, add_user_to_group: bool = True
) -> int:
    """Full install sequence. Requires sudo. Returns 0 on success.

    Steps:
      1. Bail if already_installed (idempotent).
      2. Confirm with operator unless yes=True.
      3. sudo useradd robot-md-gateway (skip if exists).
      4. Create /opt/robot-md-gateway and /etc/robot-md-gateway, and keep the
         latter root's: owned by root, writable by nobody else.
      5. sudo python3 -I -m venv /opt/robot-md-gateway/.venv, and pip install
         robot-md-gateway into it.
      6. gateway.env and bearers.yaml: create each where absent (0600,
         robot-md-gateway, `write_new_file`). An existing one keeps its
         content; if group or others can read it, or someone else owns it, it
         becomes 0600 robot-md-gateway, and the installer says what it was
         (`secure_existing_file`).
      7. Refuse a bearers.yaml the gateway would refuse or misread
         (`bearer_problems`): say why, disable the unit if it is enabled, stop.
         Warn about what either file lacks (`bearer_warnings`, `env_warnings`).
      8. Write /etc/systemd/system/robot-md-gateway.service, copy the manifest
         to /etc/robot-md-gateway/ROBOT.md, chown -R /opt/robot-md-gateway.
      9. sudo systemctl daemon-reload && systemctl enable --now robot-md-gateway
     10. Wait for the gateway's own answer (`probe_gateway`).
     11. When add_user_to_group=True (default) and $SUDO_USER is set,
         add the invoking user to the `robot-md-gateway` group so they
         can probe /dev/ttyACM* during a later `robot-md init`. The udev
         rule hardens those devices to gateway-only; without this step,
         `robot-md init`'s auto-discovery silently misses serial actuators
         and falls back to `preset: minimal`. Pass --no-add-user on
         production rigs that intentionally keep the operator account out
         of the gateway group. bearers.yaml is 0600, so the group gives that
         account no token.
     12. Print the next steps.
    """
    if already_installed():
        print("robot-md-gateway already installed and active. Nothing to do.")
        return 0

    if not yes:
        confirm = input(
            "This will sudo to create /opt/robot-md-gateway/, "
            "/etc/robot-md-gateway/, a system user, and a systemd "
            "unit. Continue? [y/N]: "
        )
        if confirm.strip().lower() not in ("y", "yes"):
            print("aborted.")
            return 2

    sudo = ["sudo"]
    steps = [
        [
            *sudo,
            "useradd",
            "--system",
            "--no-create-home",
            "--shell",
            "/usr/sbin/nologin",
            "robot-md-gateway",
        ],
        [*sudo, "mkdir", "-p", "/opt/robot-md-gateway", CONFIG_DIR],
        # The config directory stays root's, so only root can swap a name in
        # it. Earlier installs gave it to robot-md-gateway with `chown -R`.
        [*sudo, "chown", "root", CONFIG_DIR],
        [*sudo, "chmod", "go-w", CONFIG_DIR],
        [*sudo, "python3", "-I", "-m", "venv", "/opt/robot-md-gateway/.venv"],
        [*sudo, "/opt/robot-md-gateway/.venv/bin/pip", "install", "robot-md-gateway"],
    ]
    for cmd in steps:
        r = subprocess.run(cmd)
        # useradd is allowed to fail (user already exists); others must succeed.
        if r.returncode != 0 and "useradd" not in cmd:
            print(f"step failed: {' '.join(cmd)}")
            return 1

    # bearers.yaml and gateway.env are the operator's once they exist: their
    # content is never rewritten. A rerun used to rewrite both whenever the unit
    # was not active, dropping hand-added tokens and allowlist entries. Their
    # owner and mode are another matter: older installs made them 0644.
    problems: list[str] = []
    for filename, content in [
        (ENV_PATH, render_env_file(manifest_path=MANIFEST_PATH)),
        (BEARERS_PATH, render_default_bearers()),
    ]:
        result = write_new_file(filename, content, mode="0600", owner=SERVICE_OWNER, sudo=sudo)
        if result == "failed":
            print(f"failed to write {filename}")
            return 1
        if result == "created":
            print(f"created {filename} (mode 0600, {SERVICE_OWNER}).")
            continue
        state, detail = secure_existing_file(filename, owner=SERVICE_OWNER, sudo=sudo)
        if state == "failed":
            problems.append(f"{filename}: {detail}")
        elif state == "secured":
            print(
                f"{filename} exists; it was {detail}, so it is now 0600 {SERVICE_OWNER}. "
                f"Its content is unchanged."
            )
        else:
            print(f"{filename} exists; its content, owner and mode are unchanged.")

    # The bearer file is checked before the gateway is enabled: a placeholder or
    # short token would be a credential anyone can guess, and a file the
    # gateway cannot load would leave it restarting every 3 s.
    shown = subprocess.run([*sudo, "cat", BEARERS_PATH], capture_output=True, text=True)
    if shown.returncode == 0:
        problems.extend(f"{BEARERS_PATH}: {p}" for p in bearer_problems(shown.stdout))
    else:
        problems.append(f"cannot read {BEARERS_PATH}")
    if problems:
        print("the gateway cannot be enabled yet:")
        for problem in problems:
            print(f"  - {problem}")
        _disable_unit_if_enabled(sudo)
        print("Fix it with `sudoedit`, then run `robot-md install-gateway` again.")
        return 1

    env = subprocess.run([*sudo, "cat", ENV_PATH], capture_output=True, text=True)
    warnings = bearer_warnings(shown.stdout)
    warnings += env_warnings(env.stdout) if env.returncode == 0 else [f"cannot read {ENV_PATH}"]
    for warning in warnings:
        print(f"warning: {warning}")

    r = subprocess.run(
        [*sudo, "tee", "/etc/systemd/system/robot-md-gateway.service"],
        input=render_systemd_unit(),
        text=True,
        capture_output=True,
    )
    if r.returncode != 0:
        print("failed to write /etc/systemd/system/robot-md-gateway.service")
        return 1

    if manifest_path != MANIFEST_PATH:
        if os.path.exists(manifest_path):
            subprocess.run([*sudo, "cp", manifest_path, MANIFEST_PATH])
        else:
            print(
                f"warning: {manifest_path} does not exist; put the robot's ROBOT.md at "
                f"{MANIFEST_PATH}"
            )

    # Only /opt: the config directory and its files stay as set above.
    subprocess.run([*sudo, "chown", "-R", SERVICE_OWNER, "/opt/robot-md-gateway"])
    subprocess.run([*sudo, "systemctl", "daemon-reload"])
    r = subprocess.run([*sudo, "systemctl", "enable", "--now", "robot-md-gateway"])
    if r.returncode != 0:
        print("systemctl enable failed")
        return 1

    up, message = probe_gateway()
    print(message)
    if not up:
        return 1

    if add_user_to_group:
        invoker = _invoking_user()
        if invoker:
            r = subprocess.run(
                [*sudo, "usermod", "-aG", "robot-md-gateway", invoker],
                capture_output=True,
                text=True,
            )
            if r.returncode == 0:
                print(
                    f"added '{invoker}' to robot-md-gateway group "
                    "(needed for robot-md init's serial-bus probe)."
                )
                print(
                    "  → log out + back in, OR run "
                    "`newgrp robot-md-gateway` / `sg robot-md-gateway -c '<cmd>'`,\n"
                    "    before `robot-md init` so /dev/ttyACM* is readable."
                )
            else:
                print(
                    f"warning: failed to add '{invoker}' to robot-md-gateway "
                    f"group ({r.stderr.strip()}). robot-md init's serial probe "
                    f"will fail with PermissionError until you run:\n"
                    f"    sudo usermod -aG robot-md-gateway {invoker}"
                )

    print("robot-md-gateway installed and active.")
    print(NEXT_STEPS)
    return 0
