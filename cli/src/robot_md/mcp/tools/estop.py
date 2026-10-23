"""MCP tools: estop and estop_clear, both through robot-md-gateway.

`estop` sets this server's own latch first, so no further motion leaves this
server whatever happens next. Then it sends the gateway's declared stop
(`arm.estop` for so-arm101-actuator, or $ROBOT_MD_GATEWAY_STOP_TOOL). With
robot-md-gateway#35 the gateway lets a declared stop through in every safety
state, and so-arm101-actuator accepts it at every bearer tier; the actuator
latches and holds its pose. That hold is done in software. It is not a
hardware e-stop.

When the gateway does not confirm the stop, the result says so
(`stop: stop_not_confirmed`) and the MCP wrapper raises, so no client is told
a stop landed when it did not. There is no fallback that opens the serial
port, for three reasons:

- where the gateway holds the port (so-arm101-actuator claims it with flock
  and TIOCEXCL at startup), this process cannot open it;
- where the gateway is down, the port is free, and opening it here could take
  it from a gateway that is restarting, leaving the gateway unable to stop
  the arm;
- a "stop" written to the servo bus is a goal-position write, the same
  command that moves the arm, so it is not a write that can only stop.

The stop that depends on no software is the person's hardware stop.

`estop_clear` makes the robot movable again: the opposite act. It asks the
gateway for the declared clear (`arm.estop.clear`, or
$ROBOT_MD_GATEWAY_STOP_CLEAR_TOOL) under the COMMISSION scope, which the
gateway refuses below the commission tier. From a bearers file this server
reads only the actuate-tier entry, so by default the gateway refuses the
clear and the person at the machine clears the stop with their own
credential. Never in-process, never on a token. This server's latch is
released only when the gateway confirms the clear.
"""

from __future__ import annotations

import contextlib
import time

from robot_md import gateway_client
from robot_md.mcp.context import McpContext


def _audit_estop(ctx: McpContext, event: str, details: dict) -> None:
    """Append a tamper-evident entry for an e-stop set/clear.

    Setting and clearing the stop is the canonical reactive-safety action, so
    every set, clear and refused clear is recorded. No-op on unregistered
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


def estop_tool(ctx: McpContext) -> dict:
    set_at = ctx.estop.set()
    config = gateway_client.config_for_context(ctx)
    # Sent even when the config is incomplete: a stop that might land is
    # better than one never sent. The gateway decides whether it does.
    outcome = gateway_client.invoke(
        config, tool_name=config.stop_tool, tool_args={}, scope=gateway_client.STOP_SCOPE
    )
    confirmed = outcome["status"] == "ok"
    result: dict = {
        "ok": confirmed,
        "stop": "stopped" if confirmed else "stop_not_confirmed",
        "set_at": set_at,
        "local_latch": True,
        "stop_tool": config.stop_tool,
        "gateway": outcome["gateway"],
        "envelope": outcome["envelope"],
    }
    if confirmed:
        result["message"] = (
            f"The gateway ran {config.stop_tool}: the actuator latched and holds its pose. "
            "That hold is done in software; it is not a hardware e-stop. This server sends "
            "no further motion until estop_clear succeeds at the gateway."
        )
    else:
        result["error"] = outcome["error"]
        problems = f" ({' '.join(config.problems)})" if config.problems else ""
        result["message"] = (
            f"STOP NOT CONFIRMED: the gateway did not confirm {config.stop_tool} "
            f"({_reason_text(outcome['error'])}){problems}. Use the hardware stop at the "
            "machine now. This server's own latch is set, so it sends no further motion."
        )
    _audit_estop(
        ctx,
        event="estop_set",
        details={
            "set_at": set_at,
            "stop": result["stop"],
            "gateway_msg_id": (outcome["envelope"] or {}).get("msg_id"),
            "reason": None if confirmed else (outcome["error"] or {}).get("reason"),
        },
    )
    _publish(ctx, "estop.set", {"set": True, "stop": result["stop"]})
    return result


def estop_clear_tool(ctx: McpContext) -> dict:
    """Ask the gateway to clear the stop, at the commission tier."""
    config = gateway_client.config_for_context(ctx)
    if not config.ready:
        error = {
            "reason": "gateway_not_configured",
            "message": "clearing a stop goes through robot-md-gateway, and none is "
            "configured: " + " ".join(config.problems),
        }
        _audit_estop(ctx, event="estop_clear_denied", details={"reason": error["reason"]})
        return {
            "ok": False,
            "stop": "clear_not_confirmed",
            "error": error,
            "message": "Nothing was sent. This server's latch stays set.",
        }

    outcome = gateway_client.invoke(
        config, tool_name=config.stop_clear_tool, tool_args={}, scope=gateway_client.CLEAR_SCOPE
    )
    msg_id = (outcome["envelope"] or {}).get("msg_id")
    if outcome["status"] == "ok":
        ctx.estop.clear()
        cleared_at = time.time()
        _audit_estop(
            ctx,
            event="estop_cleared",
            details={"cleared_at": cleared_at, "gateway_msg_id": msg_id},
        )
        _publish(ctx, "estop.cleared", {"set": False})
        return {
            "ok": True,
            "stop": "cleared",
            "cleared_at": cleared_at,
            "gateway": outcome["gateway"],
            "envelope": outcome["envelope"],
            "message": (
                f"The gateway accepted {config.stop_clear_tool} at the commission tier, so "
                "this server's credential carries that tier. Clearing a stop is the "
                "person's decision; robot-md recommends not giving this server a "
                "commission-tier bearer."
            ),
        }

    error = outcome["error"] or {}
    _audit_estop(
        ctx,
        event="estop_clear_denied",
        details={
            "reason": error.get("reason"),
            "deny": error.get("deny"),
            "gateway_msg_id": msg_id,
        },
    )
    _publish(ctx, "estop.clear_denied", {"set": ctx.estop.is_set()})
    return {
        "ok": False,
        "stop": "clear_not_confirmed",
        "error": error,
        "gateway": outcome["gateway"],
        "envelope": outcome["envelope"],
        "message": (
            f"The gateway did not clear the stop ({_reason_text(error)}). Clearing a stop "
            "needs a commission-tier credential, which belongs to the person at the "
            "machine. This server's latch stays set."
        ),
    }
