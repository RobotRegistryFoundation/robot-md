"""Precondition evaluator — pure function from (contract, spec, runtime) to verdict.

No I/O. Returns (ok, list[PreconditionFailure]) — each failure carries a
structured record with kind, name, message, suggested_fix so MCP clients
can render actionable remediation without string-parsing the message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from robot_md.robot_spec import CapabilityContract, Precondition


@dataclass(frozen=True)
class PreconditionFailure:
    """Structured precondition-failure record for MCP clients.

    Fields:
    - kind: the precondition-kind string from the capability contract
      (e.g., 'extrinsic_present'). Machine-actionable.
    - name: optional parameter for the precondition (e.g., the pose name
      for 'pose_taught', or the skill id for 'learned_skill_ok').
    - message: human-readable description of what's missing.
    - suggested_fix: verb-form CLI hint when a single command remediates
      the failure (e.g., 'robot-md pose teach ready'). The caller is
      expected to append the robot's ROBOT.md path when executing. None
      when no single remediation command exists.
    """

    kind: str
    name: str | None
    message: str
    suggested_fix: str | None


def evaluate(
    contract: CapabilityContract,
    spec: Any,
    *,
    backend_resolved: bool,
) -> tuple[bool, list[PreconditionFailure]]:
    failed: list[PreconditionFailure] = []
    for p in contract.preconditions:
        f = _check_one(p, spec, backend_resolved=backend_resolved)
        if f is not None:
            failed.append(f)
    return (not failed, failed)


def _check_one(p: Precondition, spec: Any, *, backend_resolved: bool) -> PreconditionFailure | None:
    kind = p.kind
    if kind == "backend_resolved":
        if backend_resolved:
            return None
        return PreconditionFailure(
            kind=kind,
            name=None,
            message="no backend resolved for any driver",
            suggested_fix="check ROBOT.md drivers[] and connected hardware",
        )
    if kind == "pose_taught":
        name = p.name or "ready"
        poses = getattr(spec.physics, "poses", {}) or {}
        pose = poses.get(name)
        if pose is None or not getattr(pose, "joints", None):
            return PreconditionFailure(
                kind=kind,
                name=name,
                message=f"pose '{name}' not taught",
                suggested_fix=f"robot-md pose teach {name}",
            )
        return None
    if kind == "extrinsic_present":
        cams = getattr(spec.physics, "cameras", ()) or ()
        if not cams or all(getattr(c, "extrinsic", None) is None for c in cams):
            return PreconditionFailure(
                kind=kind,
                name=None,
                message="hand-eye extrinsic missing",
                suggested_fix="robot-md calibrate --extrinsic",
            )
        return None
    if kind == "ik_provider_set":
        solver = getattr(spec.physics, "solver", {}) or {}
        if not solver.get("ik_provider"):
            return PreconditionFailure(
                kind=kind,
                name=None,
                message="physics.solver.ik_provider not declared",
                suggested_fix="set physics.solver.ik_provider in ROBOT.md",
            )
        return None
    if kind == "workspace_declared":
        if getattr(spec.physics, "workspace", None) is None:
            return PreconditionFailure(
                kind=kind,
                name=None,
                message="physics.workspace not declared",
                suggested_fix="declare physics.workspace in ROBOT.md",
            )
        return None
    if kind == "learned_skill_ok":
        required_id = p.name
        if required_id is None:
            return PreconditionFailure(
                kind=kind,
                name=None,
                message="learned_skill_ok precondition missing 'name'",
                suggested_fix=None,
            )
        ls = getattr(spec, "learned_skills", []) or []
        found = next((s for s in ls if getattr(s, "id", None) == required_id), None)
        if found is None:
            return PreconditionFailure(
                kind=kind,
                name=required_id,
                message=f"learned skill '{required_id}' not recorded",
                suggested_fix=None,
            )
        status = getattr(found, "status", "ok")
        if status != "ok":
            return PreconditionFailure(
                kind=kind,
                name=required_id,
                message=f"learned skill '{required_id}' status={status}",
                suggested_fix=None,
            )
        return None
    return PreconditionFailure(
        kind=kind,
        name=p.name,
        message=f"unknown precondition kind '{kind}'",
        suggested_fix=None,
    )
