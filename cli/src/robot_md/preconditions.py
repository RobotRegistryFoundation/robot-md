"""Precondition evaluator — pure function from (contract, spec, runtime) to verdict.

No I/O. Returns (ok, failed_reasons). The MCP layer calls this before dispatch.
"""

from __future__ import annotations

from typing import Any

from robot_md.robot_spec import CapabilityContract, Precondition


def evaluate(
    contract: CapabilityContract,
    spec: Any,
    *,
    backend_resolved: bool,
) -> tuple[bool, list[str]]:
    failed: list[str] = []
    for p in contract.preconditions:
        reason = _check_one(p, spec, backend_resolved=backend_resolved)
        if reason is not None:
            failed.append(reason)
    return (not failed, failed)


def _check_one(p: Precondition, spec: Any, *, backend_resolved: bool) -> str | None:
    kind = p.kind
    if kind == "backend_resolved":
        return None if backend_resolved else "backend not resolved for any driver"
    if kind == "pose_taught":
        name = p.name or "ready"
        poses = getattr(spec.physics, "poses", {}) or {}
        pose = poses.get(name)
        if pose is None or not getattr(pose, "joints", None):
            return f"pose '{name}' not taught (run `robot-md pose teach {name}`)"
        return None
    if kind == "extrinsic_present":
        cams = getattr(spec.physics, "cameras", ()) or ()
        if not cams or all(getattr(c, "extrinsic", None) is None for c in cams):
            return "hand-eye extrinsic missing (run `robot-md calibrate --hand-eye`)"
        return None
    if kind == "ik_provider_set":
        solver = getattr(spec.physics, "solver", {}) or {}
        if not solver.get("ik_provider"):
            return "physics.solver.ik_provider not declared"
        return None
    if kind == "workspace_declared":
        if getattr(spec.physics, "workspace", None) is None:
            return "physics.workspace not declared"
        return None
    if kind == "learned_skill_ok":
        required_id = p.name
        if required_id is None:
            return "learned_skill_ok precondition missing 'name'"
        ls = getattr(spec, "learned_skills", []) or []
        found = next((s for s in ls if getattr(s, "id", None) == required_id), None)
        if found is None:
            return f"learned skill '{required_id}' not recorded"
        status = getattr(found, "status", "ok")
        if status != "ok":
            return f"learned skill '{required_id}' status={status}"
        return None
    return f"unknown precondition kind '{kind}'"
