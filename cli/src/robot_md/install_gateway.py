"""robot-md install-gateway subcommand.

Scaffolds the Layer 3 enforcement gateway on a fresh host:
  - Creates `robot-md-gateway` system user
  - pip-installs `robot-md-gateway` into /opt/robot-md-gateway/.venv/
  - Writes /etc/robot-md-gateway/{gateway.env, bearers.yaml, ROBOT.md}
  - Installs + enables a systemd unit
  - Verifies the gateway is reachable on 127.0.0.1:8080

Idempotent: detects an already-installed gateway and prints status without
clobbering. Requires sudo for the actual filesystem + systemd writes.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

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

[Service]
User=robot-md-gateway
Group=robot-md-gateway
WorkingDirectory=/opt/robot-md-gateway
EnvironmentFile=/etc/robot-md-gateway/gateway.env
ExecStart={_EXEC_START}
Restart=on-failure
RestartSec=3s

NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=no
DeviceAllow=/dev/ttyACM0 rw

[Install]
WantedBy=multi-user.target
"""


def render_systemd_unit(*, manifest_path: str = "/etc/robot-md-gateway/ROBOT.md") -> str:
    """Return the rendered systemd unit text. manifest_path informs the env
    file (separate write); the unit itself is invariant of manifest location."""
    return SYSTEMD_UNIT_TEMPLATE


def render_env_file(*, manifest_path: str) -> str:
    """Render the contents of /etc/robot-md-gateway/gateway.env."""
    return f"""\
ROBOT_MD_PATH={manifest_path}
ROBOT_MD_BEARERS_FILE=/etc/robot-md-gateway/bearers.yaml
ROBOT_MD_LOG_LEVEL=INFO
ROBOT_MD_TOOL_ALLOWLIST=mcp__robot__execute_capability,mcp__robot__render,mcp__robot__validate,move,home,read_state
ROBOT_MD_REQUIRE_ENVELOPE_SIGNATURE=1
"""


def render_default_bearers() -> str:
    """Render a minimal bearers.yaml. Operator must edit before first use."""
    return """\
# bearers.yaml — JWT bearers the gateway will accept on INVOKE envelopes.
# Mint with: robot-md request-apikey RRN-<your-rrn>
bearers:
  - name: operator-default
    token: "REPLACE-WITH-MINTED-TOKEN"
    rrn: "RRN-XXXXXXXXXX"
"""


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
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "active"


def install_gateway(*, manifest_path: str, yes: bool = False) -> int:
    """Full install sequence. Requires sudo. Returns 0 on success.

    Steps:
      1. Bail if already_installed (idempotent).
      2. Confirm with operator unless yes=True.
      3. sudo useradd robot-md-gateway (skip if exists).
      4. sudo python3 -m venv /opt/robot-md-gateway/.venv
      5. sudo /opt/robot-md-gateway/.venv/bin/pip install robot-md-gateway
      6. sudo write /etc/robot-md-gateway/{gateway.env, bearers.yaml, ROBOT.md (copy)}
      7. sudo chown -R robot-md-gateway:robot-md-gateway /opt/robot-md-gateway
      8. sudo write /etc/systemd/system/robot-md-gateway.service
      9. sudo systemctl daemon-reload && systemctl enable --now robot-md-gateway
     10. Verify curl 127.0.0.1:8080 returns any HTTP response.
    """
    if already_installed():
        print("robot-md-gateway already installed and active. Nothing to do.")
        return 0

    if not yes:
        confirm = input("This will sudo to create /opt/robot-md-gateway/, "
                        "/etc/robot-md-gateway/, a system user, and a systemd "
                        "unit. Continue? [y/N]: ")
        if confirm.strip().lower() not in ("y", "yes"):
            print("aborted.")
            return 2

    sudo = ["sudo"]
    steps = [
        [*sudo, "useradd", "--system", "--no-create-home", "--shell",
         "/usr/sbin/nologin", "robot-md-gateway"],
        [*sudo, "mkdir", "-p", "/opt/robot-md-gateway", "/etc/robot-md-gateway"],
        [*sudo, "python3", "-m", "venv", "/opt/robot-md-gateway/.venv"],
        [*sudo, "/opt/robot-md-gateway/.venv/bin/pip", "install",
         "robot-md-gateway"],
    ]
    for cmd in steps:
        r = subprocess.run(cmd)
        # useradd is allowed to fail (user already exists); others must succeed.
        if r.returncode != 0 and "useradd" not in cmd:
            print(f"step failed: {' '.join(cmd)}")
            return 1

    for filename, content in [
        ("/etc/robot-md-gateway/gateway.env",
         render_env_file(manifest_path=manifest_path)),
        ("/etc/robot-md-gateway/bearers.yaml", render_default_bearers()),
        ("/etc/systemd/system/robot-md-gateway.service", render_systemd_unit()),
    ]:
        r = subprocess.run(
            [*sudo, "tee", filename],
            input=content, text=True, capture_output=True,
        )
        if r.returncode != 0:
            print(f"failed to write {filename}")
            return 1

    if os.path.exists(manifest_path) and manifest_path != "/etc/robot-md-gateway/ROBOT.md":
        subprocess.run([*sudo, "cp", manifest_path, "/etc/robot-md-gateway/ROBOT.md"])

    subprocess.run([*sudo, "chown", "-R", "robot-md-gateway:robot-md-gateway",
                    "/opt/robot-md-gateway", "/etc/robot-md-gateway"])
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

    print("robot-md-gateway installed and active.")
    return 0
