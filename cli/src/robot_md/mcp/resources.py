"""MCP resource payload builders.

Each function takes an McpContext and returns a JSON-serialisable value.
Wrapped by @server.resource() in server.py. Pure — no I/O — so tests
don't need to start FastMCP.
"""

from __future__ import annotations

from typing import Any


def calibration_status(ctx: Any) -> dict[str, str]:
    """Summarise calibration state: zero cal, hand-eye extrinsic, poses.ready.

    Future refinement (v0.6.1): per-joint zero_pose_calibration check instead
    of reporting "ok" unconditionally. For now the shipped presets always
    populate zero_pose_steps, so the field is always present.
    """
    spec = ctx.spec
    poses_ready = "ok" if spec.physics.poses.get("ready") else "missing"
    cams = getattr(spec.physics, "cameras", ()) or ()
    hand_eye = (
        "ok"
        if (cams and any(getattr(c, "extrinsic", None) for c in cams))
        else "missing"
    )
    return {"zero": "ok", "hand_eye": hand_eye, "poses_ready": poses_ready}


def learned_skills(ctx: Any) -> list[dict]:
    return [
        {
            "id": s.id,
            "status": s.status,
            "validated": list(s.validated),
            "blocked_by": list(s.blocked_by),
            "notes": s.notes,
            "recorded_at": s.recorded_at,
        }
        for s in (ctx.spec.learned_skills or ())
    ]


def poses(ctx: Any) -> dict[str, dict]:
    return {
        name: {
            "joints": dict(p.joints),
            "description": p.description,
            "source": p.source,
            "taught_at": p.taught_at,
        }
        for name, p in (ctx.spec.physics.poses or {}).items()
    }
