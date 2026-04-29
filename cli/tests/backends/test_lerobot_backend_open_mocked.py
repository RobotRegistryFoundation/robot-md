from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend
from tests.backends.test_lerobot_build_config_so_arm101 import _so_arm101_spec


def _install_fake_lerobot(monkeypatch) -> tuple[MagicMock, MagicMock]:
    """Stand up enough of the lerobot package tree so the lazy import inside
    open() resolves cleanly without the real SDK installed.

    Mirrors the pyrealsense2 fake-module pattern in
    test_realsense_open_mocked.py::_install_fake_pyrealsense2.
    """
    fake_robot = MagicMock(name="lerobot_robot_instance")
    make_robot = MagicMock(name="make_robot", return_value=fake_robot)

    factory_mod = types.ModuleType("lerobot.common.robot_devices.robots.factory")
    factory_mod.make_robot = make_robot

    robots_mod = types.ModuleType("lerobot.common.robot_devices.robots")
    robots_mod.factory = factory_mod

    devices_mod = types.ModuleType("lerobot.common.robot_devices")
    devices_mod.robots = robots_mod

    common_mod = types.ModuleType("lerobot.common")
    common_mod.robot_devices = devices_mod

    root = types.ModuleType("lerobot")
    root.common = common_mod

    monkeypatch.setitem(sys.modules, "lerobot", root)
    monkeypatch.setitem(sys.modules, "lerobot.common", common_mod)
    monkeypatch.setitem(sys.modules, "lerobot.common.robot_devices", devices_mod)
    monkeypatch.setitem(sys.modules, "lerobot.common.robot_devices.robots", robots_mod)
    monkeypatch.setitem(sys.modules, "lerobot.common.robot_devices.robots.factory", factory_mod)
    return fake_robot, make_robot


def test_open_calls_make_robot_then_connect(monkeypatch) -> None:
    fake_robot, make_robot = _install_fake_lerobot(monkeypatch)
    b = LerobotBackend()
    b.open(_so_arm101_spec())

    make_robot.assert_called_once()
    cfg = make_robot.call_args[0][0]
    assert cfg["port"] == "/dev/ttyACM0"
    assert cfg["baud_rate"] == 1000000
    assert len(cfg["motors"]) == 6
    fake_robot.connect.assert_called_once()
    assert b._robot is fake_robot


def test_close_after_open_calls_disconnect(monkeypatch) -> None:
    fake_robot, _ = _install_fake_lerobot(monkeypatch)
    b = LerobotBackend()
    b.open(_so_arm101_spec())
    b.close()
    fake_robot.disconnect.assert_called_once()
    assert b._robot is None
