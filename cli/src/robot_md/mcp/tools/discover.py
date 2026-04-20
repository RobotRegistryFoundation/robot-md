"""MCP tool: discover — run the standard scene-discovery pipeline.

Steps are declarative: [{capture: {}}, {detect: {...}}, {probe_direction: {...}}].
Per-step failures are reported in the result; the tool never raises.
Tasks 18 (capture + detect) land first; Task 19 adds probe_direction.
"""

from __future__ import annotations

from typing import Any

from robot_md.detectors.hsv import DETECTORS


def discover_tool(ctx: Any, *, steps: list[dict]) -> dict:
    results: dict[str, Any] = {}
    frame = None  # cached between steps to avoid re-capturing every tick
    for step in steps:
        if not isinstance(step, dict) or len(step) != 1:
            continue
        (name, payload) = next(iter(step.items()))
        if name == "capture":
            frame = _do_capture(ctx)
            if frame is not None:
                results["capture"] = {"status": "ok", "shape": list(frame[0].shape)}
            else:
                results["capture"] = {"status": "no_frame"}
        elif name == "detect":
            if frame is None:
                frame = _do_capture(ctx)
            results["detect"] = _do_detect(ctx, frame, payload)
        elif name == "probe_direction":
            results["probe_direction"] = _do_probe(ctx, payload)
        else:
            results[name] = {"status": "unknown_step"}
    return {"status": "ok", "results": results}


def _do_capture(ctx: Any):
    backend = getattr(ctx, "backend", None)
    if backend is None:
        return None
    per = getattr(backend, "_perception", None)
    if per is None:
        return None
    return per.grab_frame()


def _do_detect(ctx: Any, frame, payload: dict) -> dict:
    if frame is None:
        return {"status": "no_frame"}
    rgb, _depth, _K = frame
    requested = list((payload or {}).get("descriptors") or [])
    out: dict[str, Any] = {}
    spec = getattr(ctx, "spec", None)
    vision = getattr(spec, "vision", None) if spec is not None else None
    for name in requested:
        desc = vision.find(name) if vision is not None else None
        if desc is None:
            out[name] = {"status": "unknown_descriptor"}
            continue
        fn = DETECTORS.get(desc.detector)
        if fn is None:
            out[name] = {"status": "unknown_detector", "detector": desc.detector}
            continue
        hit = fn(rgb, params=desc.params)
        if hit is None:
            out[name] = {"status": "not_found"}
        else:
            u, v, area = hit
            out[name] = {"status": "ok", "pixel": [u, v], "area_px2": area}
    return out


def _do_probe(ctx: Any, payload: dict) -> dict:
    """Move one joint by delta, image-diff before/after, report px shift + direction."""
    import contextlib

    import cv2
    import numpy as np

    payload = payload or {}
    joint = payload.get("joint", "shoulder_pan")
    delta = int(payload.get("delta", 30))

    backend = getattr(ctx, "backend", None)
    per = getattr(backend, "_perception", None) if backend is not None else None
    bus = getattr(backend, "_servo_bus", None) if backend is not None else None
    if per is None or bus is None:
        return {"status": "no_hardware"}

    f_before = per.grab_frame()
    if f_before is None:
        return {"status": "no_frame_before"}

    current = bus.read_positions() if hasattr(bus, "read_positions") else {}
    target = dict(current)
    target[joint] = int(current.get(joint, 2048)) + delta

    bus.torque(True)
    try:
        bus.write_positions(target)
        f_after = per.grab_frame()
    finally:
        # Best-effort return to the starting position.
        with contextlib.suppress(Exception):
            bus.write_positions(current)

    if f_after is None:
        return {"status": "no_frame_after"}

    rgb_before = cv2.cvtColor(f_before[0], cv2.COLOR_BGR2GRAY)
    rgb_after = cv2.cvtColor(f_after[0], cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(rgb_before, rgb_after)
    _, th = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
    col_sum = th.sum(axis=0)
    xs = np.arange(len(col_sum))
    total = int(col_sum.sum())
    if total == 0:
        return {"status": "no_motion_detected"}

    # Split motion mass left-of-center vs right-of-center to infer direction.
    cx = rgb_before.shape[1] / 2
    lmass = int(col_sum[xs < cx].sum())
    rmass = int(col_sum[xs >= cx].sum())

    # Empirical px-shift: the "after" column-range minus the "before" column-range.
    cols_active = xs[col_sum > 0]
    if cols_active.size == 0:
        return {"status": "no_motion_detected"}
    px_shift = int((cols_active.max() - cols_active.min()) // 2)
    direction = (
        "positive_delta→image_right" if rmass >= lmass else "positive_delta→image_left"
    )
    return {
        "status": "ok",
        "joint": joint,
        "delta": delta,
        "px_shift": px_shift,
        "direction": direction,
        "px_per_step": round(px_shift / max(1, delta), 3),
    }
