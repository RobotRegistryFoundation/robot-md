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
