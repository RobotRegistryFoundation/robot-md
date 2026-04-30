from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest

from robot_md.hotplug.service_installers.macos_launchd import write_plist

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="launchd-only test")


def test_plist_contents(tmp_path: Path) -> None:
    target = tmp_path / "dev.robotmd.hotplug.plist"
    write_plist(target=target)
    data = plistlib.loads(target.read_bytes())
    assert data["Label"] == "dev.robotmd.hotplug"
    assert "robot-md" in data["ProgramArguments"][0]
    assert data["KeepAlive"] is True
