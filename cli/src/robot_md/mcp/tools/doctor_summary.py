"""MCP tool: doctor_summary — manifest-only sanity check.

Returns a structured object with schema status, identity fields, driver
summary, HITL gates, E-stop config, and registration status.

Contract matches the npm robot-md-mcp@0.3 server's doctorSummary() function:
  schema_ok, schema_errors, robot_name, rrn, registered, dof,
  capabilities_count, drivers[], hitl_gates[], estop, notes
"""

from __future__ import annotations

from robot_md.mcp.context import McpContext
from robot_md.validate import VALID
from robot_md.validate import validate as validate_parsed


def doctor_summary_tool(ctx: McpContext) -> dict:
    """Run a manifest-only sanity check; return the npm-parity summary object."""
    parsed = ctx.parsed
    fm = parsed.frontmatter

    result = validate_parsed(parsed)
    schema_ok = result.code == VALID
    schema_errors = list(result.errors)

    md = (fm.get("metadata") or {})
    safety = (fm.get("safety") or {})
    physics = (fm.get("physics") or {})
    drivers_raw = fm.get("drivers") or []

    drivers = [
        {
            "id": d.get("id"),
            "protocol": d.get("protocol"),
            "port": d.get("port"),
            "host": d.get("host"),
        }
        for d in drivers_raw
        if isinstance(d, dict)
    ]

    gates_raw = (safety.get("hitl_gates") or [])
    hitl_gates = [
        {
            "scope": g.get("scope"),
            "require_auth": bool(g.get("require_auth", False)),
        }
        for g in gates_raw
        if isinstance(g, dict)
    ]

    rrn = md.get("rrn") or None

    return {
        "schema_ok": schema_ok,
        "schema_errors": schema_errors,
        "robot_name": md.get("robot_name"),
        "rrn": rrn,
        "registered": bool(rrn),
        "dof": physics.get("dof", 0),
        "capabilities_count": len(fm.get("capabilities") or []),
        "drivers": drivers,
        "hitl_gates": hitl_gates,
        "estop": safety.get("estop") or None,
        "notes": [
            "This is a read-only, manifest-only check. To probe live hardware "
            "(port reachability, servo response, registry lookup), run "
            "`robot-md doctor` from the shell."
        ],
    }
