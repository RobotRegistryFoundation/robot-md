"""MCP tool: discover — run the standard scene-discovery pipeline.

Steps are declarative: [{capture: {}}, {detect: {...}}, {probe_direction: {...}}].
Per-step failures are reported in the result; the tool never raises.

v0.8: emits MCP progress notifications via FastMCP Context.report_progress
(one per step) and discover.step.begin / discover.step.end events on the
dashboard substrate. Both channels are best-effort — neither can abort a
step if reporting itself fails.
"""

from __future__ import annotations

from typing import Any

from robot_md.detectors.hsv import DETECTORS


async def discover_tool(
    ctx: Any,
    *,
    steps: list[dict],
    mcp_ctx: Any | None = None,
) -> dict:
    results: dict[str, Any] = {}
    frame = None  # cached between steps to avoid re-capturing every tick
    total = len(steps)
    for i, step in enumerate(steps):
        if not isinstance(step, dict) or len(step) != 1:
            continue
        (name, payload) = next(iter(step.items()))

        _publish_step(ctx, "begin", name, i, total)
        await _report_progress(mcp_ctx, i, total, name)

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

        _publish_step(ctx, "end", name, i, total, status=results.get(name, {}).get("status"))

    return {"status": "ok", "results": results}


async def _report_progress(mcp_ctx: Any | None, i: int, total: int, name: str) -> None:
    if mcp_ctx is None:
        return
    try:
        await mcp_ctx.report_progress(i, total, name)
    except Exception:
        # Best-effort — a broken progress channel must never abort a step.
        pass


def _publish_step(
    ctx: Any,
    phase: str,
    name: str,
    i: int,
    total: int,
    *,
    status: str | None = None,
) -> None:
    publisher = getattr(ctx, "publisher", None)
    if publisher is None:
        return
    try:
        data = {"name": name, "i": i, "total": total}
        if status is not None:
            data["status"] = status
        publisher.publish(f"discover.step.{phase}", data)
    except Exception:
        pass


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
    """Move one joint by delta, image-diff before/after, report px shift + direction.

    Returns a status dict; never raises. Safety: refuses to write when the bus
    didn't report a position for the probed joint (closed bus or non-responding
    servo) — avoids commanding an absolute move anchored at a fabricated 2048.
    """
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

    try:
        current = bus.read_positions() if hasattr(bus, "read_positions") else {}
    except Exception as e:
        return {"status": "bus_error", "error": str(e)}

    if joint not in current:
        # Closed bus or non-responding servo. Refuse to write — a fabricated
        # absolute target could yank the arm.
        return {"status": "no_position_read", "joint": joint}

    target = dict(current)
    target[joint] = int(current[joint]) + delta

    f_after = None
    try:
        bus.torque(True)
        bus.write_positions(target)
        f_after = per.grab_frame()
    except Exception as e:
        return {"status": "bus_error", "error": str(e)}
    finally:
        # Best-effort return to starting position.
        import contextlib
        with contextlib.suppress(Exception):
            bus.write_positions(current)

    if f_after is None:
        return {"status": "no_frame_after"}

    # Centroid-diff formula: threshold before and after independently, compute
    # the u-centroid of each white mask, difference gives signed pixel shift.
    def _u_centroid(bgr) -> float | None:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
        col_sum = th.sum(axis=0)
        total = int(col_sum.sum())
        if total == 0:
            return None
        xs = np.arange(len(col_sum), dtype=np.float64)
        return float((xs * col_sum).sum() / total)

    c_before = _u_centroid(f_before[0])
    c_after = _u_centroid(f_after[0])
    if c_before is None or c_after is None:
        return {"status": "no_motion_detected"}

    signed = c_after - c_before
    px_shift = round(abs(signed))
    if px_shift == 0:
        return {"status": "no_motion_detected"}

    direction = (
        "positive_delta→image_right" if signed >= 0 else "positive_delta→image_left"
    )
    return {
        "status": "ok",
        "joint": joint,
        "delta": delta,
        "px_shift": px_shift,
        "direction": direction,
        "px_per_step": round(px_shift / max(1, delta), 3),
    }
