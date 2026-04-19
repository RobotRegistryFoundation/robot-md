"""Reference backend: Feetech STS3215 servos + DepthAI (OAK-D)."""

from __future__ import annotations

from robot_md.backends.base import CapabilityBackend, ExecutionResult
from robot_md.robot_spec import RobotSpec


class FeetechDepthaiBackend(CapabilityBackend):
    name = "feetech_depthai"
    protocols = frozenset({"feetech", "depthai"})
    read_only_capabilities = frozenset({"status.report", "vision.describe"})

    def __init__(self) -> None:
        self._spec: RobotSpec | None = None
        self._servo_bus = None
        self._perception = None
        self._motion = None

    def open(self, spec: RobotSpec) -> None:
        from robot_md.backends.feetech_depthai.motion import Motion
        from robot_md.backends.feetech_depthai.perception import Perception
        from robot_md.backends.feetech_depthai.servo import ServoBus

        if spec.safety.max_joint_velocity_dps is None:
            raise RuntimeError(
                "feetech_depthai backend refuses to open: "
                "safety.max_joint_velocity_dps is required"
            )
        self._spec = spec
        self._servo_bus = ServoBus.from_spec(spec)
        self._servo_bus.open()
        self._motion = Motion.from_spec(spec)
        self._perception = None
        if any(d.protocol == "depthai" for d in spec.drivers):
            try:
                self._perception = Perception.from_spec(spec)
                self._perception.open()
            except Exception:
                self._perception = None

    def close(self) -> None:
        if self._servo_bus is not None:
            try: self._servo_bus.close()
            except Exception: pass
        if self._perception is not None:
            try: self._perception.close()
            except Exception: pass
        self._servo_bus = None
        self._perception = None
        self._motion = None
        self._spec = None

    def capabilities(self) -> frozenset[str]:
        return frozenset({
            "arm.pick",
            "arm.place",
            "arm.reach",
            "vision.describe",
            "status.report",
        })

    def execute(self, capability, args, *, dry_run, estop) -> ExecutionResult:
        from robot_md.backends.feetech_depthai.capabilities import dispatch
        return dispatch(
            self, capability=capability, args=dict(args), dry_run=dry_run, estop=estop
        )

    def scene_describe(self):
        import time

        from robot_md.backends.base import SceneSnapshot

        # P3 adds perception.detect_objects; for now, scene_describe reports an empty detection list.
        detections: tuple = ()
        # grab_frame returns (rgb_ndarray, depth_ndarray, K). Encode RGB as PNG bytes
        # so SceneSnapshot.frame stays `bytes | None`-typed.
        frame: bytes | None = None
        if self._perception is not None:
            try:
                rgb, _depth, _K = self._perception.grab_frame()
                try:
                    import cv2
                    ok, encoded = cv2.imencode(".png", rgb)
                    frame = bytes(encoded.tobytes()) if ok else None
                except Exception:
                    frame = None
            except Exception:
                frame = None
        joints = self._servo_bus.read_positions() if self._servo_bus is not None else {}
        return SceneSnapshot(
            frame=frame,
            detections=detections,
            joint_state={k: float(v) for k, v in joints.items()},
            ts=time.time(),
        )
