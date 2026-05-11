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


SYSTEMD_UNIT_TEMPLATE = """\
[Unit]
Description=robot-md-gateway — enforcement gateway between agent intent and actuators
After=network-online.target
Wants=network-online.target

[Service]
User=robot-md-gateway
Group=robot-md-gateway
WorkingDirectory=/opt/robot-md-gateway
EnvironmentFile=/etc/robot-md-gateway/gateway.env
ExecStart=/opt/robot-md-gateway/.venv/bin/robot-md-gateway serve --host 127.0.0.1 --port 8080 --bearers /etc/robot-md-gateway/bearers.yaml
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
