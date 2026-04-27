"""MCP tool: spatial_eval_submit_to_rrf — Phase 1 stub passthrough."""

from __future__ import annotations

from robot_md.spatial_eval.rrf import submit_evidence


def submit_to_rrf_tool(ctx, *, run_dir: str) -> dict:
    # Phase 0: stub passthrough. The Phase 1 plan adds packet path
    # validation, signature load, and the actual RRF §27 HTTP submission.
    # Wrap with `ok` envelope key so the response shape matches the rest of
    # the spatial_eval MCP tool surface.
    result = submit_evidence(packet_path=run_dir, rcan_signature="")
    return {"ok": True, **result}
