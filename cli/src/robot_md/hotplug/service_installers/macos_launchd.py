"""launchd LaunchAgent plist writer for the hot-plug daemon."""

from __future__ import annotations

import plistlib
import shutil
from pathlib import Path


def write_plist(*, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    program = shutil.which("robot-md") or "/usr/local/bin/robot-md"
    plist = {
        "Label": "dev.robotmd.hotplug",
        "ProgramArguments": [program, "hotplug-daemon", "start"],
        "KeepAlive": True,
        "RunAtLoad": True,
    }
    with target.open("wb") as f:
        plistlib.dump(plist, f)
