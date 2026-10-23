"""robot-md install-gateway subcommand.

Scaffolds the Layer 3 enforcement gateway on a fresh host:
  - Creates `robot-md-gateway` system user
  - pip-installs `robot-md-gateway` into /opt/robot-md-gateway/.venv/
  - Writes /etc/robot-md-gateway/{gateway.env, bearers.yaml, ROBOT.md}
  - Installs + enables a systemd unit
  - Verifies the gateway is reachable on 127.0.0.1:8080

Idempotent: detects an already-installed gateway and prints status without
clobbering. It never overwrites bearers.yaml or gateway.env, even when it runs
again on a gateway that is installed but not active. Requires sudo for the
actual filesystem + systemd writes.
"""

from __future__ import annotations

import os
import secrets
import subprocess
from collections.abc import Callable
from pathlib import Path

import yaml

GATEWAY_USER = "robot-md-gateway"
BEARERS_PATH = "/etc/robot-md-gateway/bearers.yaml"
ENV_PATH = "/etc/robot-md-gateway/gateway.env"

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
DeviceAllow=/dev/ttyACM0 rw
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


def bearer_problems(text: str) -> list[str]:
    """What is wrong with a bearers.yaml, as sentences an operator can act on.
    Empty when nothing is. Refused: a file the gateway cannot load, an entry
    with no tier (a supervisor's is read), a placeholder token (anything with
    `REPLACE-WITH` in it, or starting with "<"), and a token shorter than
    MIN_TOKEN_CHARS. Tokens are never repeated back."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [f"it is not YAML ({type(exc).__name__})"]
    rows = data.get("bearers") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        return ["it has no bearer entries"]
    problems = []
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
        if row.get("tier") not in ("read", "actuate", "commission") and not (
            row.get("role") == "supervisor" and row.get("tier") in (None, "read")
        ):
            problems.append(f"{who} has no valid tier (read, actuate or commission)")
    return problems


def write_new_file(
    path: str,
    content: str,
    *,
    mode: str,
    owner: str,
    sudo: list[str] | tuple[str, ...] = ("sudo",),
    run: Callable[..., subprocess.CompletedProcess] | None = None,
) -> str:
    """Create `path` with `content`, or leave an existing file exactly as it is.

    Returns "created", "exists", or "failed". The content goes into a
    temporary file in the same directory, which `mktemp` creates 0600; it gets
    its owner and mode there, and only then its name, by link(2), which fails
    if anything already has the name. So the file is never readable by anyone
    else, not even for a moment, and a run racing another cannot replace the
    other's file. The temporary file is removed whatever happens.
    """
    sudo = list(sudo)
    run = run or subprocess.run
    if run([*sudo, "test", "-e", path]).returncode == 0:
        return "exists"
    made = run(
        [*sudo, "mktemp", os.path.join(os.path.dirname(path), ".install.XXXXXXXX")],
        capture_output=True,
        text=True,
    )
    tmp = made.stdout.strip()
    if made.returncode != 0 or not tmp:
        return "failed"
    try:
        for cmd, kw in (
            ([*sudo, "chown", owner, tmp], {}),
            ([*sudo, "chmod", mode, tmp], {}),
            ([*sudo, "tee", tmp], {"input": content, "text": True, "stdout": subprocess.DEVNULL}),
        ):
            if run(cmd, **kw).returncode != 0:
                return "failed"
        if run([*sudo, "ln", tmp, path]).returncode != 0:
            return "exists" if run([*sudo, "test", "-e", path]).returncode == 0 else "failed"
        return "created"
    finally:
        run([*sudo, "rm", "-f", tmp])


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


def install_gateway(
    *, manifest_path: str, yes: bool = False, add_user_to_group: bool = True
) -> int:
    """Full install sequence. Requires sudo. Returns 0 on success.

    Steps:
      1. Bail if already_installed (idempotent).
      2. Confirm with operator unless yes=True.
      3. sudo useradd robot-md-gateway (skip if exists).
      4. sudo python3 -m venv /opt/robot-md-gateway/.venv
      5. sudo /opt/robot-md-gateway/.venv/bin/pip install robot-md-gateway
      6. Create /etc/robot-md-gateway/gateway.env (0644) and bearers.yaml
         (0600, generated tokens) only where absent: an existing file is
         never overwritten (`write_new_file`). Refuse to go on if bearers.yaml
         has a placeholder, short or tierless token (`bearer_problems`).
      7. sudo write /etc/systemd/system/robot-md-gateway.service, copy
         ROBOT.md, sudo chown -R robot-md-gateway:robot-md-gateway
         /opt/robot-md-gateway /etc/robot-md-gateway
      8. sudo systemctl daemon-reload && systemctl enable --now robot-md-gateway
      9. Verify curl 127.0.0.1:8080 returns any HTTP response.
     10. When add_user_to_group=True (default) and $SUDO_USER is set,
         add the invoking user to the `robot-md-gateway` group so they
         can probe /dev/ttyACM* during a later `robot-md init`. The udev
         rule hardens those devices to gateway-only; without this step,
         `robot-md init`'s auto-discovery silently misses serial actuators
         and falls back to `preset: minimal`. Pass --no-add-user on
         production rigs that intentionally keep the operator account out
         of the gateway group.
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
        [*sudo, "mkdir", "-p", "/opt/robot-md-gateway", "/etc/robot-md-gateway"],
        [*sudo, "python3", "-m", "venv", "/opt/robot-md-gateway/.venv"],
        [*sudo, "/opt/robot-md-gateway/.venv/bin/pip", "install", "robot-md-gateway"],
    ]
    for cmd in steps:
        r = subprocess.run(cmd)
        # useradd is allowed to fail (user already exists); others must succeed.
        if r.returncode != 0 and "useradd" not in cmd:
            print(f"step failed: {' '.join(cmd)}")
            return 1

    # bearers.yaml and gateway.env are the operator's once they exist: never
    # overwritten. A rerun used to rewrite both whenever the unit was not
    # active, dropping hand-added tokens and allowlist entries.
    owner = f"{GATEWAY_USER}:{GATEWAY_USER}"
    for filename, content, mode in [
        (ENV_PATH, render_env_file(manifest_path=manifest_path), "0644"),
        (BEARERS_PATH, render_default_bearers(), "0600"),
    ]:
        result = write_new_file(filename, content, mode=mode, owner=owner, sudo=sudo)
        if result == "failed":
            print(f"failed to write {filename}")
            return 1
        if result == "exists":
            print(f"{filename} exists, left unchanged.")
        else:
            print(f"created {filename} (mode {mode}, {owner}).")

    # An existing bearers.yaml is checked before the gateway is enabled: a
    # placeholder or short token in it would be a credential anyone can guess.
    shown = subprocess.run([*sudo, "cat", BEARERS_PATH], capture_output=True, text=True)
    problems = (
        bearer_problems(shown.stdout) if shown.returncode == 0 else [f"cannot read {BEARERS_PATH}"]
    )
    if problems:
        print(f"{BEARERS_PATH} cannot be used yet:")
        for problem in problems:
            print(f"  - {problem}")
        print("Fix it with `sudoedit`, then run `robot-md install-gateway` again.")
        return 1

    r = subprocess.run(
        [*sudo, "tee", "/etc/systemd/system/robot-md-gateway.service"],
        input=render_systemd_unit(),
        text=True,
        capture_output=True,
    )
    if r.returncode != 0:
        print("failed to write /etc/systemd/system/robot-md-gateway.service")
        return 1

    if os.path.exists(manifest_path) and manifest_path != "/etc/robot-md-gateway/ROBOT.md":
        subprocess.run([*sudo, "cp", manifest_path, "/etc/robot-md-gateway/ROBOT.md"])

    subprocess.run(
        [
            *sudo,
            "chown",
            "-R",
            "robot-md-gateway:robot-md-gateway",
            "/opt/robot-md-gateway",
            "/etc/robot-md-gateway",
        ]
    )
    subprocess.run([*sudo, "systemctl", "daemon-reload"])
    r = subprocess.run([*sudo, "systemctl", "enable", "--now", "robot-md-gateway"])
    if r.returncode != 0:
        print("systemctl enable failed")
        return 1

    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8080/", timeout=5) as resp:
            print(f"gateway returned HTTP {resp.status}")
    except Exception as e:
        print(f"gateway started but health probe failed: {e}")
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
    return 0
