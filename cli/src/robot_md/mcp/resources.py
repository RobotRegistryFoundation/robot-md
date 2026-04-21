"""MCP resource payload builders.

Each function takes an McpContext and returns a JSON-serialisable value.
Wrapped by @server.resource() in server.py. Pure — no I/O — so tests
don't need to start FastMCP.
"""

from __future__ import annotations

import re
from typing import Any

_SAFE_URI_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _sanitize_robot_name(name: str | None) -> str:
    """Make `name` safe for MCP resource URIs.

    FastMCP rejects whitespace in URIs; slashes silently change URI
    depth. Strip everything outside [A-Za-z0-9_-], fall back to 'robot'
    if the result is empty.
    """
    if not isinstance(name, str):
        return "robot"
    cleaned = _SAFE_URI_RE.sub("-", name).strip("-")
    return cleaned or "robot"


def _safe_iter(v: Any) -> Any:
    return v if v is not None else ()


def calibration_status(ctx: Any) -> dict[str, str]:
    """Summarise calibration state: zero cal, hand-eye extrinsic, poses.ready."""
    _MISSING = {"zero": "missing", "hand_eye": "missing", "poses_ready": "missing"}
    spec = getattr(ctx, "spec", None)
    if spec is None:
        return _MISSING

    # poses.ready
    poses_attr = getattr(getattr(spec, "physics", None), "poses", {}) or {}
    poses_ready = "ok" if poses_attr.get("ready") else "missing"

    # hand_eye extrinsic
    cams = getattr(getattr(spec, "physics", None), "cameras", ()) or ()
    hand_eye = (
        "ok" if (cams and any(getattr(c, "extrinsic", None) for c in cams)) else "missing"
    )

    # zero_pose_steps — inspect per-joint. 'ok' only if every declared
    # kinematic joint carries a non-None zero_pose_steps. Missing if any
    # joint lacks it OR no kinematics declared.
    kin = getattr(getattr(spec, "physics", None), "kinematics", ()) or ()
    if not kin:
        zero = "missing"
    else:
        def _has_zero(j: Any) -> bool:
            if isinstance(j, dict):
                return j.get("zero_pose_steps") is not None
            return getattr(j, "zero_pose_steps", None) is not None

        zero = "ok" if all(_has_zero(j) for j in kin) else "missing"

    return {"zero": zero, "hand_eye": hand_eye, "poses_ready": poses_ready}


def learned_skills(ctx: Any) -> list[dict]:
    spec = getattr(ctx, "spec", None)
    if spec is None:
        return []
    return [
        {
            "id": s.id,
            "status": s.status,
            "validated": list(s.validated),
            "blocked_by": list(s.blocked_by),
            "notes": s.notes,
            "recorded_at": s.recorded_at,
        }
        for s in _safe_iter(getattr(spec, "learned_skills", ()))
    ]


def poses(ctx: Any) -> dict[str, dict]:
    spec = getattr(ctx, "spec", None)
    if spec is None:
        return {}
    poses_attr = getattr(getattr(spec, "physics", None), "poses", {}) or {}
    return {
        name: {
            "joints": dict(p.joints),
            "description": p.description,
            "source": p.source,
            "taught_at": p.taught_at,
        }
        for name, p in poses_attr.items()
    }


def recent_invocations(ctx: Any) -> list[dict]:
    """Last ≤100 paired tool.call/tool.result invocations, newest-first."""
    log = getattr(ctx, "invocation_log", None)
    if log is None:
        return []
    return log.snapshot()


def recent_errors(ctx: Any) -> list[dict]:
    """View over recent_invocations filtered to status != 'ok'."""
    log = getattr(ctx, "invocation_log", None)
    if log is None:
        return []
    return log.snapshot_errors()
