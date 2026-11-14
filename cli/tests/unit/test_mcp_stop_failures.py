"""Every way the MCP stop can fail ends in the same advice: use the hardware stop.

`estop` sends robot-md-gateway's declared stop. Whatever goes wrong on that
path (a broken signing key, a malformed gateway URL, a gateway that sends its
headers and then stalls, one that never answers, an error nobody planned
for), the reply says the stop was not confirmed and tells the person to use
the hardware stop. No exception escapes to FastMCP's generic error text, and
the stop gives up after its own short timeout, not the motion timeout.

The motion tools get the same treatment: `gateway_client.invoke` never
raises, and an answer that doesn't say whether the motion ran is reported as
an unknown outcome, never as a refusal.
"""

from __future__ import annotations

import base64
import json
import time

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from robot_md import gateway_client
from robot_md.mcp.server import build_server
from robot_md.mcp.tools.estop import estop_tool
from robot_md.mcp.tools.execute_capability import execute_capability_tool
from robot_md.mcp.tools.execute_task import execute_task_tool
from tests.unit.test_mcp_motion_through_gateway import _call, _ctx, _untouched

RRN = "RRN-000000000099"
ADVICE = "hardware stop"


def _assert_not_confirmed_with_advice(result: dict) -> None:
    assert result["ok"] is False
    assert result["stop"] == "stop_not_confirmed"
    assert ADVICE in result["message"]
    assert result["local_latch"] is True


def _write_broken_keyfile(home) -> None:
    """A keyfile that loads, and whose Ed25519 secret cannot sign."""
    keys = home / ".robot-md" / "keys"
    keys.mkdir(parents=True, exist_ok=True)
    (keys / f"{RRN}.signing.json").write_text(
        json.dumps(
            {
                "pq_kid": "deadbeef",
                "ml_dsa": {
                    "pub": base64.b64encode(b"x" * 32).decode(),
                    "sec": base64.b64encode(b"y" * 32).decode(),
                },
                "ed25519": {
                    "pub": base64.b64encode(b"z" * 32).decode(),
                    "sec": base64.b64encode(b"short").decode(),
                },
            }
        )
    )


@pytest.fixture
def fast_stop(monkeypatch):
    """Keep the timeout tests quick; the real value is pinned separately."""
    monkeypatch.setattr(gateway_client, "STOP_TIMEOUT_S", 0.5)


def test_the_stop_has_its_own_short_timeout():
    assert gateway_client.STOP_TIMEOUT_S == 2.0
    assert gateway_client.STOP_TIMEOUT_S < gateway_client.DEFAULT_TIMEOUT_S


# --------------------------------------------------------------------------
# The stop
# --------------------------------------------------------------------------


def test_a_broken_signing_key_does_not_stop_the_stop(fixtures_dir, gateway_env, tmp_path):
    """Signing failed before anything was sent, so no stop reached the gateway.
    Now a signing error leaves the envelope unsigned and the stop goes out."""
    _write_broken_keyfile(tmp_path)
    ctx = _ctx(fixtures_dir, rrn=RRN)
    r = estop_tool(ctx)
    assert r["ok"] is True, r
    assert [b["tool_name"] for b in gateway_env.bodies] == ["arm.estop"]
    assert "envelope_signature" not in gateway_env.bodies[0]
    assert "signing failed" in r["envelope"]["signing"]


def test_a_malformed_gateway_url_gives_the_advice(fixtures_dir, gateway_env, monkeypatch):
    monkeypatch.setenv(gateway_client.ENV_URL, "http//127.0.0.1:1")
    ctx = _ctx(fixtures_dir)
    r = estop_tool(ctx)
    _assert_not_confirmed_with_advice(r)
    assert ctx.estop.is_set()


async def test_a_malformed_gateway_url_is_an_mcp_error_with_the_advice(
    fixtures_dir, gateway_env, monkeypatch
):
    monkeypatch.setenv(gateway_client.ENV_URL, "http//127.0.0.1:1")
    server = build_server(_ctx(fixtures_dir))
    with pytest.raises(ToolError, match=ADVICE):
        await server.call_tool("estop", {})


def test_headers_then_a_stall_gives_the_advice(fixtures_dir, gateway_env, fast_stop):
    """The gateway sends a 403 status line and headers, then nothing."""
    gateway_env.stall_after_headers(403, 10)
    ctx = _ctx(fixtures_dir)
    t0 = time.monotonic()
    r = estop_tool(ctx)
    assert time.monotonic() - t0 < 3
    _assert_not_confirmed_with_advice(r)
    assert r["error"]["reason"] == "gateway_no_answer"


def test_a_gateway_that_never_answers_gives_up_after_the_stop_timeout(
    fixtures_dir, gateway_env, fast_stop
):
    gateway_env.hang(10)
    ctx = _ctx(fixtures_dir)
    t0 = time.monotonic()
    r = estop_tool(ctx)
    elapsed = time.monotonic() - t0
    assert elapsed < 3, f"the stop waited {elapsed:.1f} s"
    _assert_not_confirmed_with_advice(r)


def test_an_unplanned_error_in_the_stop_path_still_gives_the_advice(
    fixtures_dir, gateway_env, monkeypatch
):
    def _boom(*args, **kwargs):
        raise RuntimeError("something nobody planned for")

    monkeypatch.setattr(gateway_client, "invoke", _boom)
    ctx = _ctx(fixtures_dir)
    r = estop_tool(ctx)
    _assert_not_confirmed_with_advice(r)
    assert ctx.estop.is_set()
    assert r["error"]["reason"] == "stop_path_error"


async def test_an_unplanned_error_is_an_mcp_error_with_the_advice(
    fixtures_dir, gateway_env, monkeypatch
):
    monkeypatch.setattr(
        gateway_client, "config_for_context", lambda ctx: (_ for _ in ()).throw(KeyError("x"))
    )
    ctx = _ctx(fixtures_dir)
    server = build_server(ctx)
    with pytest.raises(ToolError, match=ADVICE):
        await server.call_tool("estop", {})
    assert ctx.estop.is_set()


# --------------------------------------------------------------------------
# Motion: invoke never raises
# --------------------------------------------------------------------------


def test_motion_with_a_malformed_url_is_refused_not_raised(fixtures_dir, gateway_env, monkeypatch):
    monkeypatch.setenv(gateway_client.ENV_URL, "http//127.0.0.1:1")
    ctx = _ctx(fixtures_dir)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "gateway_unreachable"
    assert ctx.exec_lock.acquire(blocking=False)
    ctx.exec_lock.release()
    _untouched(ctx)


def test_motion_with_a_broken_signing_key_goes_out_unsigned(fixtures_dir, gateway_env, tmp_path):
    """A gateway that requires signatures then refuses it; one that doesn't
    treats it as it treats any unsigned envelope."""
    _write_broken_keyfile(tmp_path)
    ctx = _ctx(fixtures_dir, rrn=RRN)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "ok"
    assert "envelope_signature" not in gateway_env.bodies[0]
    assert "signing failed" in r["envelope"]["signing"]


def test_motion_headers_then_a_stall_is_an_unknown_outcome(fixtures_dir, gateway_env, monkeypatch):
    monkeypatch.setenv(gateway_client.ENV_TIMEOUT, "0.5")
    gateway_env.stall_after_headers(403, 10)
    ctx = _ctx(fixtures_dir)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "gateway_no_answer"
    assert "do not resend" in r["error"]["message"]


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, {"no_ok_field": True}),
        (200, {"ok": False}),
        (200, ["not", "an", "object"]),
        (500, {"detail": "Internal Server Error"}),
        (502, {"detail": "bad gateway"}),
        (503, {"detail": "unavailable"}),
    ],
)
def test_an_answer_that_does_not_say_whether_it_ran_is_an_unknown_outcome(
    fixtures_dir, gateway_env, status, body
):
    """A 200 is the gateway's "allowed and executed", and a plain 500 can come
    after the actuator ran. Calling either "rejected" would tell Claude the
    motion didn't run."""
    gateway_env.respond(status, body)
    ctx = _ctx(fixtures_dir)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "gateway_unknown_outcome"
    assert r["error"]["http_status"] == status
    assert "may have run" in r["error"]["message"]
    assert "do not resend" in r["error"]["message"]


@pytest.mark.parametrize("status", [404, 409, 422])
def test_request_problems_are_still_rejections(fixtures_dir, gateway_env, status):
    gateway_env.respond(status, {"detail": "request problem"})
    ctx = _ctx(fixtures_dir)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["error"]["reason"] == "gateway_rejected"


def test_an_actuator_error_says_the_motion_may_have_partly_run(fixtures_dir, gateway_env):
    gateway_env.respond(
        500, {"detail": {"actuator_error": "bus timeout", "actuator_error_kind": "OSError"}}
    )
    ctx = _ctx(fixtures_dir)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["error"]["reason"] == "actuator_error"
    assert "may have" in r["error"]["note"]


# --------------------------------------------------------------------------
# A motion a stop interrupted is not reported as arrival
# --------------------------------------------------------------------------


def _interrupted(body: dict) -> dict:
    answer = dict(gateway_client_allowed(body))
    answer["telemetry"] = {"reached": False, "motion": {"stopped_by_estop": True}}
    return answer


def gateway_client_allowed(body: dict) -> dict:
    from tests.fake_gateway import FakeGateway

    return FakeGateway.allowed(body)


def test_an_interrupted_motion_reports_reached_false(fixtures_dir, gateway_env):
    gateway_env.respond(200, _interrupted({"tool_name": "arm.pick", "scope": "MANIPULATE"}))
    ctx = _ctx(fixtures_dir)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "ok"  # the gateway ran it
    assert r["reached"] is False
    assert r["stopped_by_estop"] is True
    assert "did not reach" in r["message"]


def test_a_completed_motion_reports_reached_when_the_actuator_says(fixtures_dir, gateway_env):
    answer = gateway_client_allowed({"tool_name": "arm.pick", "scope": "MANIPULATE"})
    answer["telemetry"] = {"reached": True, "motion": {"stopped_by_estop": False}}
    gateway_env.respond(200, answer)
    ctx = _ctx(fixtures_dir)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["reached"] is True
    assert r["stopped_by_estop"] is False


def test_execute_task_stops_at_a_step_that_did_not_reach(fixtures_dir, gateway_env, monkeypatch):
    from robot_md.mcp.tools import execute_task as execute_task_module
    from robot_md.planning.types import Plan, PlanStep

    plan = Plan(
        steps=(
            PlanStep(capability="arm.pick", args={}, confidence=0.99),
            PlanStep(capability="arm.place", args={}, confidence=0.99),
        ),
        raw_response={},
    )
    monkeypatch.setattr(execute_task_module, "decompose", lambda **kw: plan)
    gateway_env.respond(200, _interrupted({"tool_name": "arm.pick", "scope": "MANIPULATE"}))
    r = execute_task_tool(_ctx(fixtures_dir), prompt="pick and place")
    assert [b["tool_name"] for b in gateway_env.bodies] == ["arm.pick"]
    assert r["status"] == "not_reached"
    assert r["executions"][0]["reached"] is False


async def test_the_mcp_stop_names_the_hardware_stop_on_every_failure(
    fixtures_dir, gateway_env, fast_stop
):
    gateway_env.hang(10)
    server = build_server(_ctx(fixtures_dir))
    with pytest.raises(ToolError) as info:
        await _call(server, "estop", {})
    assert ADVICE in str(info.value)
