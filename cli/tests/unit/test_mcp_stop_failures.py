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


def test_requests_share_one_opener(fixtures_dir, gateway_env, monkeypatch):
    """Building a urllib opener loads the CA bundle for its HTTPS handler,
    about 15 ms of CPU each time. Every request built one, so a stop sent
    while reads were in flight during a motion waited behind theirs (0.94 s
    median with eight reads, against 0.33 s for 2.0.0, which refused those
    reads)."""
    import urllib.request

    built = []
    real = urllib.request.build_opener

    def counting(*handlers):
        built.append(handlers)
        return real(*handlers)

    monkeypatch.setattr(gateway_client, "_OPENER", None, raising=False)
    monkeypatch.setattr(urllib.request, "build_opener", counting)
    ctx = _ctx(fixtures_dir, extra_caps=("status.report",))
    for _ in range(2):
        r = execute_capability_tool(ctx, capability="status.report", args={}, dry_run=False)
        assert r["status"] == "ok", r
    assert estop_tool(ctx)["ok"] is True
    assert [b["tool_name"] for b in gateway_env.bodies] == [
        "status.report",
        "status.report",
        "arm.estop",
    ]
    assert len(built) == 1


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


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ("stall", "gateway_no_answer"),
        ((500, {"detail": "Internal Server Error"}), "gateway_unknown_outcome"),
        ((200, {"no_ok_field": True}), "gateway_unknown_outcome"),
        ((500, {"detail": {"actuator_error": "bus timeout"}}), "actuator_error"),
    ],
)
def test_an_unconfirmed_stop_puts_the_hardware_stop_first(
    fixtures_dir, gateway_env, fast_stop, answer, reason
):
    """For a motion whose outcome is unknown, the client says to check the
    audit record "before anything else" and not to resend it. On a stop, that
    text came before the hardware-stop advice. A stop's result now carries
    neither instruction, and its first one is the hardware stop, in the MCP
    error text too."""
    if answer == "stall":
        gateway_env.stall_after_headers(403, 10)
    else:
        gateway_env.respond(*answer)
    r = estop_tool(_ctx(fixtures_dir))
    _assert_not_confirmed_with_advice(r)
    assert r["error"]["reason"] == reason
    assert r["message"].startswith("STOP NOT CONFIRMED. Use the hardware stop at the machine now.")
    said = json.dumps({"message": r["message"], "error": r["error"]}).lower()
    assert "before anything else" not in said
    assert "resend" not in said


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


async def test_the_mcp_stop_wrapper_has_a_net_of_its_own(fixtures_dir, gateway_env, monkeypatch):
    """estop_tool never raises. If it ever did, or never ran, the MCP tool
    still answers with the hardware-stop advice instead of FastMCP's generic
    error text, and sets this server's latch so no further motion leaves."""
    from robot_md.mcp import server as server_module

    def _raises(ctx):
        raise RuntimeError("estop_tool raised")

    monkeypatch.setattr(server_module, "estop_tool", _raises)
    ctx = _ctx(fixtures_dir)
    server = build_server(ctx)
    with pytest.raises(ToolError) as info:
        await server.call_tool("estop", {})
    text = str(info.value)
    assert ADVICE in text
    assert "stop_path_error" in text
    assert ctx.estop.is_set()


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


def test_motion_with_a_broken_signing_key_refuses_and_sends_nothing(
    fixtures_dir, gateway_env, tmp_path, monkeypatch
):
    """Only the stop goes out unsigned: a stop has to get out, and
    robot-md-gateway#35 never checks a stop's signature. A motion sent
    unsigned would rely on the gateway requiring signatures, which
    `install-gateway` sets and other setups may not. 2.0.0 raised here and
    sent nothing; now the refusal has its own code and an audit entry."""
    audited = []
    monkeypatch.setattr(
        "robot_md.audit.record_event",
        lambda rrn, *, event, details: audited.append((rrn, event, details)),
    )
    _write_broken_keyfile(tmp_path)
    ctx = _ctx(fixtures_dir, rrn=RRN)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "signing_failed"
    assert "Nothing was sent" in r["error"]["message"]
    assert gateway_env.bodies == []
    assert [(rrn, d["status"], d["reason"]) for rrn, event, d in audited] == [
        (RRN, "blocked", "signing_failed")
    ]
    assert ctx.exec_lock.acquire(blocking=False)
    ctx.exec_lock.release()
    _untouched(ctx)


def test_a_read_with_a_broken_signing_key_refuses_too(fixtures_dir, gateway_env, tmp_path):
    _write_broken_keyfile(tmp_path)
    ctx = _ctx(fixtures_dir, rrn=RRN, extra_caps=("status.report",))
    r = execute_capability_tool(ctx, capability="status.report", args={}, dry_run=False)
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "signing_failed"
    assert gateway_env.bodies == []


def test_execute_task_with_a_broken_signing_key_sends_nothing(
    fixtures_dir, gateway_env, tmp_path, monkeypatch
):
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
    _write_broken_keyfile(tmp_path)
    r = execute_task_tool(_ctx(fixtures_dir, rrn=RRN), prompt="pick and place")
    assert gateway_env.bodies == []
    assert r["status"] == "blocked"
    assert [e["error"]["reason"] for e in r["executions"]] == ["signing_failed"]


def _write_unloadable_keyfile(home, how: str) -> None:
    """A key file that exists for RRN and can't be loaded."""
    keys = home / ".robot-md" / "keys"
    keys.mkdir(parents=True, exist_ok=True)
    path = keys / f"{RRN}.signing.json"
    if how == "corrupt":
        path.write_text("{not json")
    elif how == "wrong_format":
        path.write_text(json.dumps({"pq_kid": "deadbeef"}))
    elif how == "unreadable":
        # Something at the key path that reading fails on, even as root.
        path.mkdir()
    else:
        raise AssertionError(how)


UNLOADABLE = ["corrupt", "wrong_format", "unreadable"]


@pytest.mark.parametrize("how", UNLOADABLE)
def test_a_key_file_that_cannot_be_loaded_refuses_motion_and_reads(
    fixtures_dir, gateway_env, tmp_path, how
):
    """A configured key that can't be loaded is treated like one that can't
    sign. 2.0.0 sent these unsigned."""
    _write_unloadable_keyfile(tmp_path, how)
    ctx = _ctx(fixtures_dir, rrn=RRN, extra_caps=("status.report",))
    for capability in ("arm.pick", "status.report"):
        r = execute_capability_tool(ctx, capability=capability, args={}, dry_run=False)
        assert r["status"] == "blocked", (capability, r)
        assert r["error"]["reason"] == "signing_failed"
        assert "can't be loaded" in r["error"]["message"]
    assert gateway_env.bodies == []
    _untouched(ctx)


@pytest.mark.parametrize("how", UNLOADABLE)
def test_the_stop_goes_out_unsigned_when_the_key_file_cannot_be_loaded(
    fixtures_dir, gateway_env, tmp_path, how
):
    _write_unloadable_keyfile(tmp_path, how)
    r = estop_tool(_ctx(fixtures_dir, rrn=RRN))
    assert r["ok"] is True, r
    assert [b["tool_name"] for b in gateway_env.bodies] == ["arm.estop"]
    assert "envelope_signature" not in gateway_env.bodies[0]
    assert "could not load the signing keypair" in r["envelope"]["signing"]


@pytest.mark.parametrize(
    ("rrn", "note"),
    [(None, "no metadata.rrn"), (RRN, f"no signing keypair for {RRN}")],
)
def test_with_no_signing_key_configured_a_motion_goes_out_unsigned(
    fixtures_dir, gateway_env, tmp_path, rrn, note
):
    """No RRN in ROBOT.md, or no key file for it: nothing is configured to
    sign with, and the motion goes out unsigned, as in 2.0.0. The gateway's
    own setting decides whether it accepts that."""
    assert not (tmp_path / ".robot-md" / "keys").exists()
    ctx = _ctx(fixtures_dir, rrn=rrn)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "ok", r
    assert [b["tool_name"] for b in gateway_env.bodies] == ["arm.pick"]
    assert "envelope_signature" not in gateway_env.bodies[0]
    assert note in r["envelope"]["signing"]


def test_the_stop_with_a_broken_signing_key_still_goes_out_unsigned(
    fixtures_dir, gateway_env, tmp_path
):
    """The one path that keeps the unsigned fallback, with the same key that
    refuses a motion."""
    _write_broken_keyfile(tmp_path)
    ctx = _ctx(fixtures_dir, rrn=RRN)
    refused = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert refused["error"]["reason"] == "signing_failed"
    r = estop_tool(ctx)
    assert r["ok"] is True, r
    assert [b["tool_name"] for b in gateway_env.bodies] == ["arm.estop"]
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
# A redirect is followed nowhere
# --------------------------------------------------------------------------


@pytest.fixture
def elsewhere():
    """Another listener, where a redirect points."""
    from tests.fake_gateway import FakeGateway

    other = FakeGateway()
    other.start()
    yield other
    other.stop()


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_redirect_is_followed_nowhere(fixtures_dir, gateway_env, elsewhere, status):
    """A 3xx from the gateway's address carried the request, bearer and all,
    to wherever it pointed, and that listener's answer came back as the
    gateway's (2.0.0 did the same). Now the client follows none: a motion or a
    read is refused (`gateway_redirect`), the stop isn't confirmed and gives
    the hardware-stop advice, and nothing reaches the other listener."""
    target = elsewhere.url + "/v1/invoke"
    ctx = _ctx(fixtures_dir, extra_caps=("status.report",))
    for capability in ("arm.pick", "status.report"):
        gateway_env.redirect(target, status=status)
        r = execute_capability_tool(ctx, capability=capability, args={}, dry_run=False)
        assert r["status"] == "error", r
        assert r["error"]["reason"] == "gateway_redirect"
        assert r["error"]["http_status"] == status
        assert target in r["error"]["message"]
    gateway_env.redirect(target, status=status)
    stop = estop_tool(ctx)
    _assert_not_confirmed_with_advice(stop)
    assert stop["error"]["reason"] == "gateway_redirect"
    assert elsewhere.requests == []
    assert elsewhere.get_requests == []


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
    text = str(info.value)
    assert ADVICE in text
    # The advice leads: it comes before the envelope and the error details.
    assert text.index(ADVICE) < text.index('"envelope"') < text.index('"error"')
