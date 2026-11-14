"""MCP tools: estop (through robot-md-gateway) and estop_clear (refused here).

`estop` sets this server's own latch first. From then on this server sends no
motion: the motion tools check the latch before they prepare a request and
again just before they send it. (A motion request already being sent can
still reach the gateway after the stop; so-arm101-actuator's motions consult
its stop latch first.) The tools run in worker threads, so the stop is not
queued behind a motion waiting on the gateway. Then `estop` sends the
gateway's declared stop (`arm.estop` for so-arm101-actuator, or
$ROBOT_MD_GATEWAY_STOP_TOOL), waiting at most `STOP_TIMEOUT_S` (2 s) for the
answer. With robot-md-gateway#35 the gateway lets a declared stop through in
every safety state, and so-arm101-actuator accepts it at every bearer tier;
the actuator latches and holds its pose. That hold is done in software. It is
not a hardware e-stop.

On a gateway without robot-md-gateway#35 (0.5.0a9 and earlier) a stop has to
pass every gate a motion does, so a manifest-pin mismatch, a missing signing
key or a failed key lookup refuses it, and the gateway does not stop the arm
when heartbeats stop. The MCP server warns at startup when it finds such a
gateway, and works with either.

Whatever goes wrong on the stop's path, the result says the stop was not
confirmed (`stop: stop_not_confirmed`) and, before any reason, tells the
person to use the hardware stop, and the MCP wrapper raises, so no client is
told a stop landed when it did not. There is no fallback that opens the serial port, for three
reasons:

- where the gateway holds the port (so-arm101-actuator claims it with flock
  and TIOCEXCL at startup), this process cannot open it;
- where the gateway is down, the port is free, and opening it here could take
  it from a gateway that is restarting, leaving the gateway unable to stop
  the arm;
- a "stop" written to the servo bus is a goal-position write, the same
  command that moves the arm, so it is not a write that can only stop.

The stop that depends on no software is the person's hardware stop.

`estop_clear` makes the robot movable again: the opposite act, and the
person's. This server sends nothing for it. It refuses, and says how the
person clears the stop with their own commission-tier credential. This
server's latch is released only when the server restarts: neither
so-arm101-actuator nor robot-md-gateway reports the actuator's latch in any
read (`arm.state` and `status.report` carry no latch), so this server cannot
tell reliably that the person cleared it.
"""

from __future__ import annotations

import contextlib

from robot_md import gateway_client
from robot_md.mcp.context import McpContext

HARDWARE_STOP_ADVICE = "Use the hardware stop at the machine now."


def _audit_estop(ctx: McpContext, event: str, details: dict) -> None:
    """Append a tamper-evident entry for an e-stop set or a refused clear.

    Setting and clearing the stop is the canonical reactive-safety action, so
    every set and every clear request is recorded. No-op on unregistered
    manifests; audit failures must never crash the stop itself. The gateway
    keeps its own, signed record; `gateway_msg_id` ties this entry to it.
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

    with contextlib.suppress(Exception):
        record_event(rrn, event=event, details={"tool": "estop", **details})


def _publish(ctx: McpContext, kind: str, data: dict) -> None:
    if getattr(ctx, "publisher", None) is not None:
        with contextlib.suppress(Exception):
            ctx.publisher.publish(kind, data)


def _reason_text(error: dict | None) -> str:
    error = error or {}
    deny = error.get("deny")
    message = error.get("message")
    if deny:
        return f"{deny}: {message}"
    return str(message or error.get("reason") or "no reason given")


def for_a_stop(error: dict) -> dict:
    """The gateway client's error, reworded where its words fit only a motion.

    For a motion whose outcome is unknown, the client says to check the audit
    record "before anything else" and not to resend it, and an actuator error
    notes that part of the motion may have run. A stop's first instruction is
    the hardware stop, so a stop's result carries none of those. The reason
    codes stay as they are.
    """
    out = dict(error)
    reason = out.get("reason")
    if reason == "gateway_no_answer":
        cause = out.get("cause")
        out["message"] = (
            "the gateway gave no complete answer"
            + (f" ({cause})" if cause else "")
            + ", so this server can't tell whether the stop landed"
        )
    elif reason == "gateway_unknown_outcome":
        out["message"] = (
            f"the gateway answered HTTP {out.get('http_status')} without a decision this "
            "server can read, so it can't tell whether the stop landed"
        )
    elif reason == "actuator_error":
        out["note"] = "The actuator raised while running the stop, so the arm may not be holding."
    return out


def not_confirmed(
    *,
    set_at: float | None,
    stop_tool: str,
    error: dict,
    gateway: dict | None = None,
    envelope: dict | None = None,
    problems: tuple[str, ...] = (),
) -> dict:
    """The one shape every unconfirmed stop takes. The hardware-stop advice is
    the first thing its message says, and the message comes before the details,
    so it leads the MCP error text too."""
    detail = f" ({' '.join(problems)})" if problems else ""
    return {
        "ok": False,
        "stop": "stop_not_confirmed",
        "message": (
            f"STOP NOT CONFIRMED. {HARDWARE_STOP_ADVICE} The gateway did not confirm "
            f"{stop_tool} ({_reason_text(error)}){detail}. This server's own latch is set, "
            "so it sends no further motion."
        ),
        "set_at": set_at,
        "local_latch": True,
        "stop_tool": stop_tool,
        "gateway": gateway,
        "envelope": envelope,
        "error": error,
    }


def estop_tool(ctx: McpContext) -> dict:
    """Latch this server, then send the gateway's declared stop. Never raises."""
    set_at = None
    # The latch failing to set must not keep the stop from going out.
    with contextlib.suppress(Exception):
        set_at = ctx.estop.set()
    stop_tool = gateway_client.DEFAULT_STOP_TOOL
    try:
        config = gateway_client.config_for_context(ctx)
        stop_tool = config.stop_tool
        # Sent even when the config is incomplete: a stop that might land is
        # better than one never sent. The gateway decides whether it does.
        outcome = gateway_client.invoke(
            config,
            tool_name=config.stop_tool,
            tool_args={},
            scope=gateway_client.STOP_SCOPE,
            timeout_s=gateway_client.STOP_TIMEOUT_S,
            # The only request that goes out unsigned when the key can't
            # sign: a stop has to get out.
            unsigned_if_signing_fails=True,
        )
        confirmed = outcome["status"] == "ok"
        if confirmed:
            result: dict = {
                "ok": True,
                "stop": "stopped",
                "set_at": set_at,
                "local_latch": True,
                "stop_tool": config.stop_tool,
                "gateway": outcome["gateway"],
                "envelope": outcome["envelope"],
                "message": (
                    f"The gateway ran {config.stop_tool}: the actuator latched and holds "
                    "its pose. That hold is done in software; it is not a hardware "
                    "e-stop. This server sends no further motion until it restarts, and "
                    "the person clears the actuator with their own credential."
                ),
            }
        else:
            result = not_confirmed(
                set_at=set_at,
                stop_tool=config.stop_tool,
                error=for_a_stop(outcome["error"] or {"reason": "not_confirmed"}),
                gateway=outcome["gateway"],
                envelope=outcome["envelope"],
                problems=tuple(config.problems),
            )
    except Exception as e:  # every failure on this path ends in the advice
        result = not_confirmed(
            set_at=set_at,
            stop_tool=stop_tool,
            error={
                "reason": "stop_path_error",
                "message": f"{type(e).__name__} in the stop path; the stop may not have been sent",
            },
        )
    warnings = list(getattr(ctx, "gateway_warnings", None) or ())
    if warnings:
        result["warnings"] = warnings
    _audit_estop(
        ctx,
        event="estop_set",
        details={
            "set_at": set_at,
            "stop": result["stop"],
            "gateway_msg_id": (result.get("envelope") or {}).get("msg_id"),
            "reason": None if result["ok"] else (result.get("error") or {}).get("reason"),
        },
    )
    _publish(ctx, "estop.set", {"set": True, "stop": result["stop"]})
    return result


def clear_instructions(
    stop_tool: str = gateway_client.DEFAULT_STOP_CLEAR_TOOL,
    manifest: str = str(gateway_client.INSTALL_GATEWAY_MANIFEST_FILE),
) -> str:
    """How the person clears a stop. `manifest` is the ROBOT.md the gateway
    pins, the path this server's own requests name; with any other path the
    gateway refuses the clear (`manifest_pin`)."""
    return (
        "Clearing a stop makes the robot movable again, so it is the person's to do, "
        "at the machine, with their own commission-tier credential; this server never "
        "holds one and sends nothing. The person: (1) if robot-md-gateway tripped (only "
        "a gateway with robot-md-gateway#35 or later trips; it answers "
        "`deny: safety_state`), clears it with POST /v1/safety/clear and the commission "
        "token while heartbeats are arriving from the supervisor's device. Where the "
        "gateway requires signed envelopes, as install-gateway sets it, that clear must be "
        "a signed ESTOP_CLEAR, and the token alone is refused; robot-md-gateway's own "
        "`clear` command builds it (robot-md-gateway#36, not merged yet). "
        f"(2) clears the actuator's latch with {stop_tool} at the commission tier: "
        f"`robot-md invoke {manifest} --tool {stop_tool} --scope COMMISSION "
        "--bearer <their commission token>`, naming the ROBOT.md the gateway pins. "
        "(3) reconnects this MCP server (/mcp, robot-md, Reconnect), which releases its "
        "own latch. Until then this server sends no motion."
    )


def clear_refusal(
    stop_tool: str = gateway_client.DEFAULT_STOP_CLEAR_TOOL,
    manifest: str = str(gateway_client.INSTALL_GATEWAY_MANIFEST_FILE),
) -> dict:
    """The refusal `estop_clear` answers with, without this server's latch
    state. The dashboard's clear button shows the same."""
    instructions = clear_instructions(stop_tool, manifest)
    return {
        "ok": False,
        "stop": "not_cleared",
        "error": {"reason": "person_clears_stops", "message": instructions},
        "message": instructions,
    }


def estop_clear_tool(ctx: McpContext) -> dict:
    """Refuse: clearing a stop is the person's. Sends nothing, keeps the latch."""
    stop_clear_tool = gateway_client.DEFAULT_STOP_CLEAR_TOOL
    manifest = str(gateway_client.INSTALL_GATEWAY_MANIFEST_FILE)
    with contextlib.suppress(Exception):
        config = gateway_client.config_for_context(ctx)
        stop_clear_tool = config.stop_clear_tool
        manifest = config.manifest_path or manifest
    latched = True
    with contextlib.suppress(Exception):
        latched = bool(ctx.estop.is_set())
    _audit_estop(
        ctx,
        event="estop_clear_refused",
        details={"reason": "person_clears_stops", "latched": latched},
    )
    _publish(ctx, "estop.clear_refused", {"set": latched})
    refusal = clear_refusal(stop_clear_tool, manifest)
    return {
        "ok": refusal["ok"],
        "stop": refusal["stop"],
        "local_latch": latched,
        "error": refusal["error"],
        "message": refusal["message"],
    }
