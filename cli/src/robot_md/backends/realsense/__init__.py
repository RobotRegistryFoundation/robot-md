"""RealSense camera adapter — perception only, no motion."""

from __future__ import annotations

from robot_md.backends.base import (
    CapabilityBackend,
    ExecutionResult,
    SceneSnapshot,
)
from robot_md.robot_spec import RobotSpec


class RealsenseBackend(CapabilityBackend):
    name = "realsense"
    protocols = frozenset({"realsense"})
    read_only_capabilities = frozenset({"perceive.rgb", "perceive.depth"})

    def __init__(self) -> None:
        self._pipeline = None

    def open(self, spec: RobotSpec) -> None:
        import pyrealsense2 as rs

        self._pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
        config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        self._pipeline.start(config)

    def close(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()
            self._pipeline = None

    def capabilities(self) -> frozenset[str]:
        return frozenset(
            {
                "perceive.rgb",
                "perceive.depth",
                "realsense.aligned_depth",
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
        from robot_md.backends.realsense.capabilities import dispatch

        return dispatch(self, capability=capability, args=dict(args), dry_run=dry_run, estop=estop)

    def scene_describe(self) -> SceneSnapshot:
        # Implemented in Task 13.
        return SceneSnapshot.empty()
