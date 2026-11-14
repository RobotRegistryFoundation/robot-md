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
- ROBOT.md has a ``hitl_gates[]`` entry that needs a person (``hitl_gate``).
  Such a gate covers every motion (see ``robot_md.motion_gates``), so on
  robot-md's presets and examples/bob.ROBOT.md, which gate `destructive`
  and `system`, every motion is refused;
- a declared precondition fails (``precondition``);
- another motion from this server is still in flight (``busy``). Reads are
  not held back by a motion in flight;
- a signing key is configured and can't be loaded, or loads and can't sign
  (``signing_failed``). Only the stop goes out unsigned then. With no key
  configured, requests go out unsigned, as in 2.0.0.

There is no confirmation token. The one this tool used to take was written by
the model, and any non-empty string satisfied the gate; a token the model
writes is not a person's confirmation.

``status: ok`` means the gateway ran the call. A stop can interrupt a motion
the gateway ran, so the result carries the actuator's ``reached`` and
``stopped_by_estop`` when it reports them.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from robot_md import gateway_client, motion_gates
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
        warnings = list(getattr(ctx, "gateway_warnings", None) or ())
        if warnings:
            result["warnings"] = warnings
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
    # Checked here and again just before sending: the tools run in worker
    # threads, so a stop can land in between.
    if not is_read and (latched := _latch_error(ctx)) is not None:
        return _finish(_blocked(**latched))

    config = gateway_client.config_for_context(ctx)
    if not config.ready:
        result = _error(
            "gateway_not_configured",
            "motion goes through robot-md-gateway, and none is configured: "
            + " ".join(config.problems),
        )
        result["gateway_config"] = config.describe()
        return _finish(result)

    gate = None if is_read else _match_hitl_gate(ctx, capability)
    if gate is not None:
        # TODO(out-of-band confirmation): a person's confirmation for a gated
        # motion has to reach the gateway by a path the model cannot write:
        # the plan is that the gateway holds the gated request until the
        # pendant signs an approval bound to that exact request, and that the
        # gateway stops trusting a caller-written `delegation_chain`. When that
        # exists, this check defers to it. Until then a gated motion does not
        # run from MCP, and on a manifest whose gates cover every motion (bob)
        # no motion runs from MCP at all.
        scope = gate.get("scope")
        result = _blocked(
            "hitl_gate",
            f"ROBOT.md's gate '{scope}' needs a person's confirmation, and a gate that "
            "needs one covers every motion on this robot. That confirmation has to come "
            "from outside this conversation, and robot-md has no such path yet, so this "
            "server refuses every motion while the gate stands. Reads still work. A reply "
            "in chat is not that confirmation.",
        )
        result["error"]["scope"] = scope
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

    scope = gateway_client.OBSERVE_SCOPE if is_read else motion_gates.motion_scope_for(capability)

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

    if is_read:
        # Reads are not held back by a motion in flight: the state stays
        # readable while the arm moves.
        outcome = gateway_client.invoke(config, tool_name=capability, tool_args=args, scope=scope)
        return _finish(_from_outcome(outcome))

    if not ctx.exec_lock.acquire(blocking=False):
        return _finish(_blocked("busy", "another motion from this server is in flight"))
    try:
        # The latch is checked again after the envelope is signed, just before
        # it is sent. A stop set during the send itself can reach the gateway
        # before or after this motion: before, and so-arm101-actuator's latch
        # refuses the motion; after, and the stop interrupts it (the gateway
        # runs declared stops on lanes of their own).
        outcome = gateway_client.invoke(
            config,
            tool_name=capability,
            tool_args=args,
            scope=scope,
            withhold=lambda: _latch_error(ctx),
        )
    finally:
        ctx.exec_lock.release()
    return _finish(_from_outcome(outcome))


def _from_outcome(outcome: dict) -> dict:
    result = {
        "status": outcome["status"],
        "trajectory": None,
        "events": [],
        "error": outcome["error"],
        "gateway": outcome["gateway"],
        "envelope": outcome["envelope"],
    }
    if outcome["status"] == "ok":
        report = gateway_client.motion_report(outcome["gateway"])
        result.update(report)
        if report.get("reached") is False:
            result["message"] = (
                "The gateway ran it, and the arm did not reach the target"
                + (" because a stop interrupted it." if report.get("stopped_by_estop") else ".")
                + " Don't send the next step as if it had."
            )
    return result


_LATCH_MESSAGE = (
    "this MCP server's stop latch is set, so it sends no motion. Only a restart of "
    "this server releases it (/mcp, robot-md, Reconnect), after the person has "
    "cleared the stop at the gateway with their own credential."
)


def _latch_error(ctx: McpContext) -> dict | None:
    """The refusal ({reason, message}) while this server's stop latch is set."""
    if ctx.estop.is_set():
        return {"reason": "estop_set", "message": _LATCH_MESSAGE}
    return None


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
    """The `hitl_gates[]` entry that refuses this motion, if any. A gate that
    needs a person covers every motion: see `robot_md.motion_gates`."""
    spec = ctx.spec
    if spec is None:
        return None
    return motion_gates.gate_for_motion(spec.safety.hitl_gates)


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
