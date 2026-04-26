"""MCP tool: vision.find — descriptor_id → camera-frame XYZ (mm)."""

from __future__ import annotations

from typing import Any

import numpy as np

from robot_md.detectors.hsv import DETECTORS


def _pixel_to_3d(u: int, v: int, depth_mm: float, K) -> tuple[float, float, float]:
    if depth_mm is None or depth_mm <= 0:
        return (float("nan"), float("nan"), float("nan"))
    fx, fy = float(K[0, 0]), float(K[1, 1])
    cx, cy = float(K[0, 2]), float(K[1, 2])
    return ((u - cx) * depth_mm / fx, (v - cy) * depth_mm / fy, float(depth_mm))


def vision_find_tool(ctx: Any, *, descriptor_id: str) -> dict:
    if ctx.backend is None:
        return _err("no_backend", "backend not resolved")
    desc = ctx.spec.vision.find(descriptor_id) if ctx.spec else None
    if desc is None:
        return _err(
            "unknown_descriptor",
            f"no vision.object_descriptors entry with id={descriptor_id!r}",
        )
    detector = DETECTORS.get(desc.detector)
    if detector is None:
        return _err("unknown_detector", f"detector '{desc.detector}' not implemented")
    per = getattr(ctx.backend, "_perception", None)
    if per is None:
        return _err("no_perception", "backend has no perception module")
    frame = per.grab_frame()
    if frame is None:
        return _err("no_frame", "grab_frame returned None")
    rgb, depth, K = frame
    hit = detector(rgb, params=desc.params, depth_frame=depth)
    if hit is None:
        return {"status": "not_found", "descriptor": descriptor_id}
    u, v, area = hit
    # Sample depth with a small patch around (u, v) for robustness against holes.
    # Clamp so huge detections don't median across background. A 31x31
    # patch (r=15) is enough for robust depth-hole filling without
    # sampling beyond the object.
    r = min(15, max(3, int((area**0.5) // 4)))
    h, w = depth.shape
    patch = depth[max(0, v - r) : min(h, v + r + 1), max(0, u - r) : min(w, u + r + 1)].astype(
        np.float32
    )
    # Filter out OAK-D's 65535 "no data" sentinel — without this, sparse
    # valid pixels in a textureless patch are dwarfed by the saturated
    # background and the median lands at ~15m even for objects at 40cm.
    valid = patch[(patch > 0) & (patch < 10000)]
    depth_mm = float(np.median(valid)) if valid.size else float("nan")
    xyz = _pixel_to_3d(u, v, depth_mm, K)
    return {
        "status": "ok",
        "descriptor": descriptor_id,
        "pixel": [u, v],
        "depth_mm": depth_mm,
        "camera_xyz_mm": list(xyz),
        "area_px2": area,
    }


def _err(reason: str, msg: str) -> dict:
    return {"status": "error", "error": {"reason": reason, "message": msg}}
