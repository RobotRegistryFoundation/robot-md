"""Which ROBOT.md `safety.hitl_gates[]` entries make robot-md refuse a motion.

robot-md's MCP server refuses a motion that a gate needing a person covers,
because no path for that person's confirmation exists yet: a reply in the
chat is not one, and the model must not be able to write one. This module
decides which gates cover motion. The rule:

- **A gate needs a person** unless it says `require_auth: false`. One that
  doesn't say is read as needing one (robot-md-gateway reads it as not).
- **A gate that needs a person covers every motion**, whatever its scope
  names, with one exception: a scope robot-md-gateway maps only to non-motion
  scopes (`commission` -> COMMISSION) covers none.

Why every motion, and not only the capabilities a scope seems to name:
robot-md-gateway reads `destructive` as MANIPULATE and `system` as EXECUTE
and ACTUATE (`HiTLPolicy.from_manifest_gates`), and for a tool that moves it
treats a gate on any motion scope as a gate on all of them
(`requires(scope, motion=True)`), because the scope label is caller-written.
The capability name is caller-chosen too: a gate on `arm` or on `arm.pick`
that `arm.move_to` or `gripper.close` walks past is not a gate. A scope
neither layer recognizes (`mobile_base`, `nav-high-speed`) is read the same
way; the gateway ignores those, so this is the only layer that keeps them.

Read-only capabilities are never covered: they cannot move the robot.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

#: robot_md_gateway.cert.gates._MANIFEST_GATE_SCOPE_MAP, mirrored. A test
#: checks it against the installed gateway.
MANIFEST_GATE_SCOPES: dict[str, frozenset[str]] = {
    "destructive": frozenset({"MANIPULATE"}),
    "system": frozenset({"EXECUTE", "ACTUATE"}),
    "commission": frozenset({"COMMISSION"}),
}

#: robot_md_gateway.cert.policy.MOTION_SCOPES, mirrored.
MOTION_SCOPES = frozenset({"MANIPULATE", "NAVIGATE", "ACTUATE", "EXECUTE"})

#: Envelope scope per capability family. For a tool its actuator declares as
#: motion, the gateway applies the strictest motion scope whatever the label;
#: for an undeclared tool the label decides which gates apply, and it reads
#: correctly in the audit trail.
_FAMILY_SCOPES = {"arm": "MANIPULATE", "gripper": "MANIPULATE", "nav": "NAVIGATE"}
FALLBACK_MOTION_SCOPE = "ACTUATE"


def motion_scope_for(capability: str) -> str:
    """The envelope scope for a capability that moves the robot."""
    return _FAMILY_SCOPES.get(capability.split(".", 1)[0], FALLBACK_MOTION_SCOPE)


def requires_person(gate: Any) -> bool:
    """A gate needs a person unless it says `require_auth: false`."""
    return isinstance(gate, Mapping) and gate.get("require_auth") is not False


def _scope(gate: Mapping) -> str:
    scope = gate.get("scope")
    return scope.strip().lower() if isinstance(scope, str) else ""


def coverage(gate: Mapping) -> str:
    """What one gate covers: "all_motion" or "none" (see the module docstring)."""
    if not requires_person(gate):
        return "none"
    mapped = MANIFEST_GATE_SCOPES.get(_scope(gate))
    if mapped is not None and not (mapped & MOTION_SCOPES):
        return "none"
    return "all_motion"


def gates_covering_motion(gates: Iterable[Any]) -> list[dict]:
    """The gates under which robot-md's MCP server refuses every motion."""
    return [dict(g) for g in gates or () if isinstance(g, Mapping) and coverage(g) == "all_motion"]


def gate_for_motion(gates: Iterable[Any]) -> dict | None:
    """The first gate that refuses motion, or None. Call it only for a
    capability that can move the robot; reads are never gated, and every
    motion gets the same answer."""
    covering = gates_covering_motion(gates)
    return covering[0] if covering else None


__all__ = [
    "FALLBACK_MOTION_SCOPE",
    "MANIFEST_GATE_SCOPES",
    "MOTION_SCOPES",
    "coverage",
    "gate_for_motion",
    "gates_covering_motion",
    "motion_scope_for",
    "requires_person",
]
