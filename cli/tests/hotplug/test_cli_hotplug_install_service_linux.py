from __future__ import annotations

import sys
from pathlib import Path

import pytest

from robot_md.hotplug.service_installers.linux_systemd import write_unit_file


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="systemd-only test")


def test_unit_file_contents(tmp_path: Path) -> None:
    target = tmp_path / "robot-md-hotplug.service"
    write_unit_file(target=target)
    text = target.read_text()
    assert "[Unit]" in text and "[Service]" in text and "[Install]" in text
    assert "robot-md hotplug-daemon start" in text
    assert "Restart=on-failure" in text
    assert "WantedBy=default.target" in text
