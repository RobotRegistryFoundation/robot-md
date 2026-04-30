"""systemd --user unit file writer for the hot-plug daemon."""

from __future__ import annotations

from pathlib import Path

_TEMPLATE = """[Unit]
Description=robot-md hot-plug daemon
After=network.target

[Service]
ExecStart=robot-md hotplug-daemon start
Restart=on-failure
RestartPreventExitStatus=2

[Install]
WantedBy=default.target
"""


def write_unit_file(*, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_TEMPLATE)
