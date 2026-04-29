from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def test_perceive_rgb_pulls_from_robot_capture() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    robot.capture_observation.return_value = {
        "observation.images.front": b"FRAME_RGB_BYTES",
    }
    b._robot = robot
    result = b.execute("perceive.rgb", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    payload = result.events[-1].data
    assert payload["frame_bytes"] == b"FRAME_RGB_BYTES"
    assert payload["source"] == "observation.images.front"


def test_perceive_rgb_dry_run() -> None:
    b = LerobotBackend()
    b._robot = MagicMock()
    result = b.execute("perceive.rgb", {}, dry_run=True, estop=None)
    assert result.status == "ok"
    b._robot.capture_observation.assert_not_called()


def test_perceive_rgb_no_camera_returns_error() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    robot.capture_observation.return_value = {"observation.depth.front": b"DEPTH_ONLY"}
    b._robot = robot
    result = b.execute("perceive.rgb", {}, dry_run=False, estop=None)
    assert result.status == "error"
    assert result.error["reason"] == "no_camera"


def test_perceive_depth_pulls_from_observation() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    robot.capture_observation.return_value = {
        "observation.depth.front": b"DEPTH_BYTES",
    }
    b._robot = robot
    result = b.execute("perceive.depth", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    payload = result.events[-1].data
    assert payload["frame_bytes"] == b"DEPTH_BYTES"


def test_perceive_depth_returns_no_depth_when_camera_absent() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    robot.capture_observation.return_value = {
        "observation.images.front": b"COLOR_ONLY",
    }
    b._robot = robot
    result = b.execute("perceive.depth", {}, dry_run=False, estop=None)
    assert result.status == "error"
    assert result.error["reason"] == "no_depth_camera"
