"""LeRobot adapter — motion + camera, wraps HuggingFace LeRobot SDK."""

from __future__ import annotations

import contextlib

from robot_md.backends.base import (
    CapabilityBackend,
    ExecutionResult,
    SceneSnapshot,
)
from robot_md.robot_spec import RobotSpec


class LerobotBackend(CapabilityBackend):
    name = "lerobot"
    protocols = frozenset({"feetech", "dynamixel"})
    read_only_capabilities = frozenset({"perceive.rgb", "perceive.depth"})

    def __init__(self) -> None:
        self._robot = None

    def open(self, spec: RobotSpec) -> None:
        from lerobot.common.robot_devices.robots.factory import make_robot

        from robot_md.backends.lerobot.config import build_lerobot_config

        cfg = build_lerobot_config(spec)
        self._robot = make_robot(cfg)
        self._robot.connect()

    def close(self) -> None:
        if self._robot is not None:
            with contextlib.suppress(Exception):
                self._robot.disconnect()
            self._robot = None

    def capabilities(self) -> frozenset[str]:
        return frozenset(
            {
                "arm.pick",
                "arm.place",
                "arm.home",
                "perceive.rgb",
                "perceive.depth",
                "gripper.open",
                "gripper.close",
                "lerobot.teleop",
            }
        )

    def execute(
        self,
        capability: str,
        args: dict,
        *,
        dry_run: bool,
        estop,
    ) -> ExecutionResult:
        from robot_md.backends.lerobot.capabilities import dispatch

        return dispatch(self, capability=capability, args=dict(args), dry_run=dry_run, estop=estop)

    def scene_describe(self) -> SceneSnapshot:
        return SceneSnapshot.empty()
