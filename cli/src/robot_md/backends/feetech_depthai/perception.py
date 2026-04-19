"""OAK-D perception pipeline + 3D back-projection.

Ports the depthai usage from `examples/tier0/05_scene_snapshot.py`.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any

from robot_md.robot_spec import RobotSpec

RGB_SIZE = (1280, 720)  # width, height
DEPTH_SIZE = (640, 400)
WARMUP_FRAMES = 20


@dataclass
class Perception:
    driver_id: str
    K: Any = None
    _pipe: Any = None
    _rgb_q: Any = None
    _depth_q: Any = None
    _rgb_w: int = RGB_SIZE[0]
    _rgb_h: int = RGB_SIZE[1]

    @classmethod
    def from_spec(cls, spec: RobotSpec) -> Perception:
        cam = next(iter(spec.physics.cameras), None)
        return cls(driver_id=cam.driver_id if cam else "none")

    def open(self) -> None:
        try:
            import depthai as dai
            import numpy as np
        except Exception as e:
            raise RuntimeError(f"depthai (or numpy) not available: {e}") from e

        # Read calibration (exclusive device access) first.
        with dai.Device() as cal_dev:
            mat = cal_dev.readCalibration().getCameraIntrinsics(
                dai.CameraBoardSocket.CAM_A,
                self._rgb_w,
                self._rgb_h,
            )
        self.K = np.array(mat, dtype=np.float64)

        pipe = dai.Pipeline()
        pipe.__enter__()
        try:
            rgb_cam = pipe.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
            rgb_out = rgb_cam.requestOutput(size=RGB_SIZE, type=dai.ImgFrame.Type.NV12)
            self._rgb_q = rgb_out.createOutputQueue()

            left = pipe.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
            right = pipe.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)
            left_out = left.requestOutput(size=DEPTH_SIZE, type=dai.ImgFrame.Type.NV12)
            right_out = right.requestOutput(size=DEPTH_SIZE, type=dai.ImgFrame.Type.NV12)

            stereo = pipe.create(dai.node.StereoDepth)
            stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
            stereo.setOutputSize(self._rgb_w, self._rgb_h)
            stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.FAST_ACCURACY)
            left_out.link(stereo.left)
            right_out.link(stereo.right)
            self._depth_q = stereo.depth.createOutputQueue()

            pipe.start()
            self._pipe = pipe
        except Exception:
            pipe.__exit__(None, None, None)
            raise

    def close(self) -> None:
        if self._pipe is not None:
            with contextlib.suppress(Exception):
                self._pipe.__exit__(None, None, None)
        self._pipe = None
        self._rgb_q = None
        self._depth_q = None
        self.K = None

    def grab_frame(self) -> tuple[Any, Any, Any] | None:
        """Capture one warmed-up aligned RGB+depth pair.

        Returns (rgb_ndarray, depth_ndarray, K) or None if not opened.
        depth is uint16, millimeters.
        """
        if self._rgb_q is None or self._depth_q is None:
            return None
        rgb_frame = None
        depth_frame = None
        for _ in range(WARMUP_FRAMES):
            rgb_msg = self._rgb_q.get()
            depth_msg = self._depth_q.get()
            if rgb_msg is not None:
                rgb_frame = rgb_msg.getCvFrame()
            if depth_msg is not None:
                depth_frame = depth_msg.getFrame()
        if rgb_frame is None or depth_frame is None:
            raise RuntimeError("failed to capture frame from OAK-D")
        return rgb_frame, depth_frame, self.K

    def detect_objects(self) -> list[dict]:
        """Return [{class, bbox_xyxy, conf}]. Stubbed for now."""
        return []


def _pixel_to_3d(u: int, v: int, depth_mm: float, K: Any) -> tuple[float, float, float]:
    """Back-project a pixel + depth into camera-frame XYZ (mm)."""
    if depth_mm <= 0:
        return (float("nan"), float("nan"), float("nan"))
    fx, fy = float(K[0, 0]), float(K[1, 1])
    cx, cy = float(K[0, 2]), float(K[1, 2])
    z = float(depth_mm)
    x = (u - cx) * z / fx
    y = (v - cy) * z / fy
    return (x, y, z)
