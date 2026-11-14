"""MCP tool: hotplug_confirm — bind or reject a pending hot-plug event."""

from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.manifest import merge as manifest_merge
from robot_md.hotplug.matcher import BindProposal
from robot_md.hotplug.queue import AlreadyResolvedError, EventQueue, _safe_iter_records


def hotplug_confirm_tool(
    *,
    event_id: str,
    decision: str,
    choice_index: int | None = None,
    _queue: EventQueue | None = None,
    _manifest_path: Path | None = None,
    _by: str = "claude",
) -> dict:
    if decision not in {"bind", "reject"}:
        return {"ok": False, "error": f"decision must be 'bind' or 'reject', got {decision!r}"}

    q = _queue or EventQueue()
    manifest_path = _manifest_path or Path.cwd() / "ROBOT.md"

    records, _ = _safe_iter_records(q.path)
    target = next(
        (r for r in records if r.get("kind") == "pending" and r.get("id") == event_id),
        None,
    )
    if target is None:
        return {"ok": False, "error": f"event {event_id!r} not found"}

    # Check before any write. A repeated bind used to merge the driver into
    # ROBOT.md a second time and only then learn from the queue that the
    # event was already resolved.
    resolved = next(
        (r for r in records if r.get("kind") == "resolved" and r.get("ref") == event_id),
        None,
    )
    if resolved is not None:
        return {"ok": False, "error": "already_resolved", "by": resolved.get("by") or "unknown"}

    if decision == "reject":
        try:
            q.append_resolution(ref_id=event_id, resolution="reject", by=_by, outcome=None)
        except AlreadyResolvedError as e:
            return {"ok": False, "error": "already_resolved", "by": e.by}
        return {"ok": True}

    # decision == "bind"
    decision_blob = target["decision"]
    proposals = []
    if decision_blob.get("bind_proposal"):
        proposals.append(decision_blob["bind_proposal"])
    proposals.extend(decision_blob.get("alternatives", []) or [])
    if not proposals:
        return {"ok": False, "error": "no bind_proposal available for this event"}
    if choice_index is None:
        choice_index = 0
    if choice_index < 0 or choice_index >= len(proposals):
        return {
            "ok": False,
            "error": f"choice_index {choice_index} out of range (0..{len(proposals) - 1})",
        }
    chosen = proposals[choice_index]
    proposal_obj = BindProposal(
        rrn=chosen.get("rrn"),
        driver_id_suggestion=chosen["driver_id_suggestion"],
        backend_name=chosen["backend_name"],
        preset_name=chosen.get("preset_name"),
        capability_preview=[],
        inferred_fields=chosen.get("inferred_fields") or {},
    )

    outcome = manifest_merge(proposal_obj, manifest_path=manifest_path)
    if not outcome.success:
        return {"ok": False, "error": "merge_failed", "reason": outcome.reason}

    try:
        q.append_resolution(
            ref_id=event_id,
            resolution="bind",
            by=_by,
            outcome={"driver_id": outcome.driver_id, "rrn": outcome.rrn},
        )
    except AlreadyResolvedError as e:
        return {"ok": False, "error": "already_resolved", "by": e.by}
    return {"ok": True, "driver_id": outcome.driver_id}
