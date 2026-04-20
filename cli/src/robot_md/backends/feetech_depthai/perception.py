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
    _spec: Any = None  # stashed so vision_find can resolve descriptors without the caller re-passing

    @classmethod
    def from_spec(cls, spec: RobotSpec) -> Perception:
        cam = next(iter(spec.physics.cameras), None)
        return cls(driver_id=cam.driver_id if cam else "none", _spec=spec)

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

    def detect_objects(self, *, descriptors: list | None = None) -> list[dict]:
        if not descriptors:
            return []
        from robot_md.detectors.hsv import DETECTORS

        frame = self.grab_frame()
        if frame is None:
            return []
        rgb, _depth, _K = frame
        out: list[dict] = []
        for d in descriptors:
            fn = DETECTORS.get(d.detector)
            if fn is None:
                continue
            hit = fn(rgb, params=d.params)
            if hit is not None:
                u, v, area = hit
                out.append({"id": d.id, "pixel": [u, v], "area_px2": area})
        return out

    def vision_find(self, *, descriptor: str, spec: Any = None) -> dict:
        """Find a single named descriptor in the current frame.

        Returns a dict with `status` ∈ {"ok", "no_match", "error"}. When `ok`,
        also sets `xyz_cam_mm` as a (x, y, z) tuple in camera frame (mm).
        Uses the HSV detector registry + pinhole back-projection, sampling a
        patch of depth pixels around the centroid for robustness against
        stereo holes (mirrors `mcp.tools.vision_find.vision_find_tool`).
        """
        from robot_md.detectors.hsv import DETECTORS

        active_spec = spec if spec is not None else getattr(self, "_spec", None)
        if active_spec is None:
            return {"status": "error", "descriptor": descriptor, "reason": "no_spec"}
        vision = getattr(active_spec, "vision", None)
        if vision is None:
            return {"status": "error", "descriptor": descriptor, "reason": "no_vision_block"}
        descr = vision.find(descriptor) if hasattr(vision, "find") else None
        if descr is None:
            return {"status": "error", "descriptor": descriptor, "reason": "descriptor_not_declared"}

        fn = DETECTORS.get(descr.detector)
        if fn is None:
            return {"status": "error", "descriptor": descriptor,
                    "reason": f"detector_unknown:{descr.detector}"}

        frame = self.grab_frame()
        if frame is None:
            return {"status": "error", "descriptor": descriptor, "reason": "no_frame"}
        rgb, depth, K = frame

        # Auto-derive depth bounds from workspace + extrinsic when not already set.
        descriptor_params_effective = dict(descr.params)
        ignore_ws = bool(descriptor_params_effective.get("ignore_workspace_bounds"))
        has_manual_bounds = (
            descriptor_params_effective.get("min_depth_mm") is not None
            or descriptor_params_effective.get("max_depth_mm") is not None
        )
        if not ignore_ws and not has_manual_bounds:
            try:
                from robot_md.detectors.hsv import workspace_depth_bounds

                active_spec_for_ws = spec if spec is not None else getattr(self, "_spec", None)
                cam0 = active_spec_for_ws.physics.cameras[0]
                extrinsic = cam0.extrinsic
                ws = active_spec_for_ws.physics.workspace
                if extrinsic is not None and ws is not None and ws.bounds_mm:
                    lo, hi = workspace_depth_bounds(ws.bounds_mm, list(extrinsic))
                    descriptor_params_effective["min_depth_mm"] = lo
                    descriptor_params_effective["max_depth_mm"] = hi
            except (KeyError, TypeError, AttributeError, IndexError):
                pass  # workspace or extrinsic missing — skip depth filter silently

        depth_frame_for_detector = depth if (
            descriptor_params_effective.get("min_depth_mm") is not None
            or descriptor_params_effective.get("max_depth_mm") is not None
        ) else None

        hit = fn(rgb, params=descriptor_params_effective, depth_frame=depth_frame_for_detector)
        if hit is None:
            return {"status": "no_match", "descriptor": descriptor}
        u, v, area = hit

        import numpy as np

        # Patch-based depth sampling — median of valid pixels around (u, v)
        # survives stereo holes better than a single-pixel lookup.
        r = min(15, max(3, int((area ** 0.5) // 4)))
        h, w = depth.shape
        patch = depth[max(0, v - r): min(h, v + r + 1),
                      max(0, u - r): min(w, u + r + 1)].astype(np.float32)
        valid = patch[patch > 0]
        if valid.size == 0:
            return {"status": "no_match", "descriptor": descriptor, "reason": "invalid_depth"}
        depth_mm = float(np.median(valid))
        xyz = _pixel_to_3d(u, v, depth_mm, K)
        return {
            "status": "ok",
            "descriptor": descriptor,
            "xyz_cam_mm": xyz,
            "pixel": (int(u), int(v)),
            "depth_mm": depth_mm,
            "area_px2": area,
        }


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
