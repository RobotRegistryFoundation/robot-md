from __future__ import annotations

from robot_md.backends.base import ExecutionEvent, ExecutionResult


def perceive_rgb(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    if dry_run:
        return ExecutionResult(
            status="ok",
            trajectory=None,
            events=[ExecutionEvent(kind="dry_run", data={"capability": "perceive.rgb"})],
            error=None,
        )
    frames = backend._pipeline.wait_for_frames(timeout_ms=1000)
    color = frames.get_color_frame()
    data = bytes(color.get_data()) if color is not None else b""
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[ExecutionEvent(kind="frame", data={"frame_bytes": data, "format": "bgr8"})],
        error=None,
    )


def perceive_depth(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    if dry_run:
        return ExecutionResult(
            status="ok",
            trajectory=None,
            events=[ExecutionEvent(kind="dry_run", data={"capability": "perceive.depth"})],
            error=None,
        )
    frames = backend._pipeline.wait_for_frames(timeout_ms=1000)
    depth = frames.get_depth_frame()
    data = bytes(depth.get_data()) if depth is not None else b""
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[ExecutionEvent(kind="frame", data={"frame_bytes": data, "format": "z16"})],
        error=None,
    )
