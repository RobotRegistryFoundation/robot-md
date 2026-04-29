"""LeRobot perception handlers — wrap the connected robot's capture_observation()."""

from __future__ import annotations

from robot_md.backends.base import ExecutionEvent, ExecutionResult


def _first_image_key(obs: dict, prefix: str) -> str | None:
    for k in obs:
        if k.startswith(prefix):
            return k
    return None


def perceive_rgb(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    if dry_run:
        return ExecutionResult(
            status="ok",
            trajectory=None,
            events=[ExecutionEvent(kind="dry_run", data={"capability": "perceive.rgb"})],
            error=None,
        )
    obs = backend._robot.capture_observation()
    key = _first_image_key(obs, "observation.images.")
    if key is None:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={
                "reason": "no_camera",
                "detail": "no observation.images.* in observation dict",
            },
        )
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[
            ExecutionEvent(
                kind="frame",
                data={"frame_bytes": obs[key], "format": "bgr8", "source": key},
            )
        ],
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
    obs = backend._robot.capture_observation()
    key = _first_image_key(obs, "observation.depth.")
    if key is None:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={
                "reason": "no_depth_camera",
                "detail": "no observation.depth.* in observation dict",
            },
        )
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[
            ExecutionEvent(
                kind="frame",
                data={"frame_bytes": obs[key], "format": "z16", "source": key},
            )
        ],
        error=None,
    )
