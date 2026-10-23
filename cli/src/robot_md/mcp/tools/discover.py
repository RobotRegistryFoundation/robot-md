"""MCP tool: discover — run the standard scene-discovery pipeline.

Steps are declarative: [{capture: {}}, {detect: {...}}, {probe_direction: {...}}].
Per-step failures are reported in the result; the tool never raises.

capture and detect read the camera. probe_direction used to move a joint by
writing the servo bus from this process; robot-md's MCP server no longer
writes the bus, so that step now refuses (see `_do_probe`).

v0.8: emits MCP progress notifications via FastMCP Context.report_progress
(one per step) and discover.step.begin / discover.step.end events on the
dashboard substrate. Both channels are best-effort — neither can abort a
step if reporting itself fails.
"""

from __future__ import annotations

import contextlib
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
    # Best-effort — a broken progress channel must never abort a step.
    with contextlib.suppress(Exception):
        await mcp_ctx.report_progress(i, total, name)


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
    """Refuse. This step moved one joint by `delta` and diffed the image.

    It wrote the servo bus from this process, with no gate, no tier and no
    stop check. robot-md's MCP server no longer writes the bus: motion goes
    through robot-md-gateway, which has no probe tool yet. Nothing here
    touches the bus, whatever the backend holds.
    """
    payload = payload or {}
    return {
        "status": "refused",
        "joint": payload.get("joint", "shoulder_pan"),
        "message": (
            "probe_direction moves a joint, and robot-md's MCP server sends motion "
            "only through robot-md-gateway, which has no probe tool. Nothing was "
            "moved. capture and detect still work."
        ),
    }
