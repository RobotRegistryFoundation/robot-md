"""MCP tool: execute_capability — one declared capability, sent to robot-md-gateway.

The MCP server does not move the robot. This tool builds an RCAN INVOKE
envelope for the capability and sends it to robot-md-gateway's
``POST /v1/invoke``. The gateway decides: bearer tier, tool allowlist, scope,
manifest and its own safety state. The actuator behind it bounds and paces
the motion, and the gateway records the decision in its audit trail. This
tool reports the gateway's answer as given.

It refuses, and sends nothing, when:

- the capability is not declared in ROBOT.md (``not_declared``);
- this server's own stop latch is set (``estop_set``), except for read-only
  capabilities;
- no gateway is configured (``gateway_not_configured``);
- the capability's scope matches a ``hitl_gates[]`` entry that requires
  authorization (``hitl_gate``);
- a declared precondition fails (``precondition``);
- another call from this server is still in flight (``busy``).

There is no confirmation token. The one this tool used to take was written by
the model, and any non-empty string satisfied the gate; a token the model
writes is not a person's confirmation.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from robot_md import gateway_client
from robot_md.mcp.context import McpContext

#: Capabilities that read and never move, whatever the backend declares. They
#: still go to the gateway, under the OBSERVE scope, and they pass this
#: server's own stop latch so the robot's state can be read after a stop. A
#: capability wrongly listed here still cannot move anything through the
#: gateway, which refuses a motion tool sent under OBSERVE (`tool_scope`).
READ_ONLY_CAPABILITIES = frozenset(
    {"status.report", "vision.describe", "arm.state", "perceive.rgb", "perceive.depth"}
)


def execute_capability_tool(
    ctx: McpContext,
    *,
    capability: str,
    args: dict[str, Any],
    dry_run: bool,
) -> dict:
    # Publish tool.call before any early exit so EVERY invocation reaches the
    # InvocationLog and events.jsonl, refusals included.
    request_id = f"{capability}-{int(time.time() * 1000)}"
    if getattr(ctx, "publisher", None) is not None:
        ctx.publisher.publish(
            "tool.call",
            {
                "tool": "execute_capability",
                "capability": capability,
                "args": args,
                "dry_run": dry_run,
                "request_id": request_id,
            },
        )

    def _finish(result: dict) -> dict:
        _publish_result(ctx, request_id, capability, result)
        return result

    declared = ctx.spec.capabilities if ctx.spec is not None else frozenset()
    if capability not in declared:
        return _finish(
            _error("not_declared", f"capability '{capability}' not in spec.capabilities")
        )

    read_only = _read_only_capabilities(ctx)
    is_read = capability in read_only

    # This server's own latch, set by `estop`. It only ever withholds: while
    # it is set, no motion leaves this server, whatever the gateway would say.
    if ctx.estop.is_set() and not is_read:
        return _finish(
            _blocked(
                "estop_set",
                "this MCP server's stop latch is set, so it sends no motion. It is "
                "released only when the gateway accepts estop_clear (commission "
                "tier) or the server restarts.",
            )
        )

    config = gateway_client.config_for_context(ctx)
    if not config.ready:
        result = _error(
            "gateway_not_configured",
            "motion goes through robot-md-gateway, and none is configured: "
            + " ".join(config.problems),
        )
        result["gateway_config"] = config.describe()
        return _finish(result)

    gate = _match_hitl_gate(ctx, capability)
    if gate is not None and gate.get("require_auth") is not False:
        # TODO(out-of-band confirmation): a person's confirmation for a gated
        # scope has to reach the gateway by a path the model cannot write,
        # such as the pendant, or a confirmation the gateway asks for and
        # verifies itself. When one exists, this check defers to it. Until
        # then a gated capability does not run from MCP. (The gateway's own
        # HiTL check reads a `delegation_chain` from the envelope, which this
        # server never writes for the same reason.)
        result = _blocked(
            "hitl_gate",
            f"ROBOT.md gates scope '{gate.get('scope')}' with require_auth. That needs "
            "a person's confirmation from outside this conversation, and robot-md "
            "has no such path yet, so this server refuses it. A reply in chat is not "
            "that confirmation.",
        )
        result["error"]["scope"] = gate.get("scope")
        return _finish(result)

    # Preconditions are manifest checks (taught pose, extrinsic, ...). Read-only
    # capabilities skip them, as before: observability must survive
    # calibration gaps. `backend_resolved` means an executor is configured,
    # which is the gateway; whether its actuator holds the device is the
    # gateway's to answer.
    if not is_read:
        contract = ctx.spec.capability_contracts.get(capability) if ctx.spec else None
        if contract is not None and contract.preconditions:
            from dataclasses import asdict

            from robot_md.preconditions import evaluate

            ok, failures = evaluate(contract, ctx.spec, backend_resolved=True)
            if not ok:
                return _finish(
                    {
                        "status": "blocked",
                        "trajectory": None,
                        "events": [],
                        "error": {
                            "reason": "precondition",
                            "preconditions": [asdict(f) for f in failures],
                        },
                    }
                )

    scope = gateway_client.OBSERVE_SCOPE if is_read else gateway_client.MOTION_SCOPE

    if dry_run:
        # Built exactly as it would be sent, and not sent: no request leaves
        # this process on a dry run.
        envelope, _note = gateway_client.prepare_envelope(
            config, tool_name=capability, tool_args=args, scope=scope, sign=False
        )
        return _finish(
            {
                "status": "dry_run",
                "trajectory": None,
                "events": [],
                "error": None,
                "dry_run": gateway_client.envelope_preview(config, envelope),
            }
        )

    if not ctx.exec_lock.acquire(blocking=False):
        return _finish(_blocked("busy", "another call from this server is in flight"))
    try:
        outcome = gateway_client.invoke(config, tool_name=capability, tool_args=args, scope=scope)
    finally:
        ctx.exec_lock.release()
    return _finish(
        {
            "status": outcome["status"],
            "trajectory": None,
            "events": [],
            "error": outcome["error"],
            "gateway": outcome["gateway"],
            "envelope": outcome["envelope"],
        }
    )


def _read_only_capabilities(ctx: McpContext) -> frozenset[str]:
    backend = getattr(ctx, "backend", None)
    declared = getattr(backend, "read_only_capabilities", frozenset()) if backend else frozenset()
    return READ_ONLY_CAPABILITIES | frozenset(declared)


def _error(reason: str, message: str) -> dict:
    return {
        "status": "error",
        "trajectory": None,
        "events": [],
        "error": {"reason": reason, "message": message},
    }


def _blocked(reason: str, message: str) -> dict:
    return {
        "status": "blocked",
        "trajectory": None,
        "events": [],
        "error": {"reason": reason, "message": message},
    }


def _match_hitl_gate(ctx: McpContext, capability: str) -> dict | None:
    """The `hitl_gates[]` entry whose scope is the capability's prefix
    (`arm` for `arm.pick`) or the capability itself, if any."""
    spec = ctx.spec
    if spec is None:
        return None
    cap_scope = capability.split(".", 1)[0]
    for gate in spec.safety.hitl_gates:
        scope = gate.get("scope") if isinstance(gate, dict) else None
        if scope in (cap_scope, capability):
            return gate if isinstance(gate, dict) else None
    return None


def _publish_result(ctx: McpContext, request_id: str, capability: str, result: dict) -> None:
    _audit_invocation(ctx, capability, result, request_id)
    if getattr(ctx, "publisher", None) is None:
        return
    ctx.publisher.publish(
        "tool.result",
        {
            "tool": "execute_capability",
            "capability": capability,
            "status": result.get("status"),
            "request_id": request_id,
            "error": result.get("error"),
        },
    )


def _audit_invocation(ctx: McpContext, capability: str, result: dict, request_id: str) -> None:
    """Append a tamper-evident entry to the per-robot audit log for every
    capability invocation outcome — including allows, denials, and estop
    blocks. No-op when the manifest has no rrn (unregistered robots have
    no chain to bind audits to). The gateway keeps its own, signed record;
    `gateway_msg_id` ties this entry to it.
    """
    rrn = None
    spec = getattr(ctx, "spec", None)
    if spec is not None:
        meta = getattr(spec, "metadata", None)
        if meta is not None:
            rrn = getattr(meta, "rrn", None)
    if not rrn:
        return
    from robot_md.audit import record_event

    err = result.get("error") or {}
    details = {
        "tool": "execute_capability",
        "capability": capability,
        "request_id": request_id,
        "status": result.get("status"),
        "reason": err.get("reason"),
    }
    scope = err.get("scope")
    if scope is not None:
        details["scope"] = scope
    envelope = result.get("envelope") or {}
    if envelope.get("msg_id"):
        details["gateway_msg_id"] = envelope["msg_id"]
    if err.get("deny"):
        details["deny"] = err["deny"]
    # Audit failure must never crash a capability call. The deployer gets
    # the audit chain integrity guarantee from `audit verify`.
    with contextlib.suppress(Exception):
        record_event(rrn, event="capability_invocation", details=details)
