from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.config import HotplugConfig


def test_defaults_when_no_config_file(tmp_path: Path) -> None:
    cfg = HotplugConfig.load(path=tmp_path / "hotplug.toml")
    assert cfg.pending_ttl_days == 7.0


def test_overrides_from_toml(tmp_path: Path) -> None:
    p = tmp_path / "hotplug.toml"
    p.write_text("pending_ttl_days = 3\n")
    cfg = HotplugConfig.load(path=p)
    assert cfg.pending_ttl_days == 3
