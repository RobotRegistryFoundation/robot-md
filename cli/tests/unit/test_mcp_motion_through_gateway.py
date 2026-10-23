"""MCP motion goes through robot-md-gateway, and through nothing else.

The MCP server used to move the arm itself: `execute_capability` and
`execute_task` called the backend in-process, which wrote to the servo bus, and
the gate in front of it accepted any non-empty `confirm_token` the model
supplied. These tests pin the replacement:

1. no MCP tool writes to the servo bus in-process, and the server never opens
   the bus;
2. with no configured or reachable gateway, the motion tools refuse;
3. each motion is one envelope to the gateway's POST /v1/invoke, shaped the
   way the gateway reads it, and the gateway's answer is reported as given;
4. `confirm_token` authorizes nothing: the parameter is gone, and a token
   passed anyway changes nothing.

The gateway here is `tests.fake_gateway.FakeGateway`, on 127.0.0.1. Nothing
touches hardware.
"""

from __future__ import annotations

import base64
import inspect
import json
import socket
import threading
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from mcp.server.fastmcp.exceptions import ToolError
from rcan.audit_bundle import canonical_json

from robot_md import gateway_client
from robot_md.backends.base import CapabilityBackend, ExecutionResult
from robot_md.mcp.context import load_context
from robot_md.mcp.server import build_server
from robot_md.mcp.tools import execute_task as execute_task_module
from robot_md.mcp.tools.estop import estop_clear_tool, estop_tool
from robot_md.mcp.tools.execute_capability import execute_capability_tool
from robot_md.mcp.tools.execute_task import execute_task_tool
from robot_md.planning.types import Plan, PlanStep
from robot_md.robot_spec import RobotSpec
from tests.conftest import TEST_BEARER, TEST_RURI

MANIFEST = "robot_md_oak_d_factory_cal.yaml"

#: Every key the gateway's envelope reader may receive from this client.
ENVELOPE_KEYS = {
    "msg_id",
    "type",
    "ruri",
    "scope",
    "tool_name",
    "tool_args",
    "manifest_path",
    "nonce",
    "timestamp_ms",
    "actuator_name",
    "envelope_signature",
}
#: Keys that would claim a human decision. The gateway's HiTL gate reads
#: `delegation_chain`; none of these may ever be written by the MCP server.
HUMAN_CLAIM_KEYS = {"delegation_chain", "human_subject", "confirm_token", "payload"}


class _RecordingBus:
    """Records every write. The MCP server must never produce one."""

    def __init__(self) -> None:
        self.writes: list[tuple] = []

    def read_positions(self) -> dict[str, int]:
        return {"shoulder_pan": 2048, "shoulder_lift": 2048}

    def write_positions(self, positions):
        self.writes.append(("write_positions", dict(positions)))

    def torque(self, on):
        self.writes.append(("torque", on))

    def interpolate(self, *args, **kwargs):
        self.writes.append(("interpolate", args, kwargs))


class _RecordingBackend(CapabilityBackend):
    """A backend that would move the arm in-process if anything called it."""

    name = "recording"
    protocols = frozenset({"feetech", "depthai"})
    read_only_capabilities = frozenset({"status.report"})

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.opened: list[str] = []
        self._servo_bus = _RecordingBus()
        self._perception = None

    def open(self, spec):
        self.opened.append("open")

    def open_perception(self, spec):
        self.opened.append("open_perception")

    def close(self):
        pass

    def capabilities(self):
        return frozenset({"arm.pick", "arm.place", "arm.home", "status.report"})

    def execute(self, capability, args, *, dry_run, estop):
        self.executed.append(capability)
        self._servo_bus.write_positions({"shoulder_pan": 0})
        return ExecutionResult(status="ok", trajectory=[], events=[], error=None)


def _ctx(fixtures_dir: Path, *, extra_caps=(), gates=None, rrn=None):
    ctx = load_context(fixtures_dir / MANIFEST)
    fm = ctx.parsed.frontmatter
    for cap in extra_caps:
        fm["capabilities"].append(cap)
    if gates is not None:
        fm.setdefault("safety", {})["hitl_gates"] = gates
    if rrn is not None:
        fm.setdefault("metadata", {})["rrn"] = rrn
    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.backend = _RecordingBackend()
    return ctx


def _untouched(ctx) -> None:
    assert ctx.backend.executed == [], "the backend executed a capability in-process"
    assert ctx.backend._servo_bus.writes == [], "the servo bus was written in-process"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _call(server, name: str, args: dict) -> dict:
    """Call a FastMCP tool and return its dict result."""
    out = await server.call_tool(name, args)
    if isinstance(out, tuple):
        out = out[1]
    if isinstance(out, dict) and set(out) == {"result"}:
        out = out["result"]
    if isinstance(out, list):  # content blocks
        out = json.loads(out[0].text)
    return out


# --------------------------------------------------------------------------
# 1. No in-process bus writes
# --------------------------------------------------------------------------


def test_execute_capability_never_calls_the_backend_or_the_bus(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir)
    r = execute_capability_tool(
        ctx, capability="arm.pick", args={"target": "red_lego"}, dry_run=False
    )
    assert r["status"] == "ok", r
    _untouched(ctx)
    assert len(gateway_env.requests) == 1


def test_execute_capability_works_with_no_backend_at_all(fixtures_dir, gateway_env):
    """The executor is the gateway. The server needs no backend to send motion."""
    ctx = _ctx(fixtures_dir)
    ctx.backend = None
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "ok", r
    assert gateway_env.bodies[0]["tool_name"] == "arm.pick"


def test_execute_task_sends_every_step_to_the_gateway(fixtures_dir, gateway_env, monkeypatch):
    plan = Plan(
        steps=(
            PlanStep(capability="arm.pick", args={"target": "red_lego"}, confidence=0.99),
            PlanStep(capability="arm.place", args={"target": "bowl"}, confidence=0.99),
        ),
        raw_response={},
    )
    monkeypatch.setattr(execute_task_module, "decompose", lambda **kw: plan)
    ctx = _ctx(fixtures_dir)
    r = execute_task_tool(ctx, prompt="put the lego in the bowl")
    assert r["status"] == "ok", r
    assert [b["tool_name"] for b in gateway_env.bodies] == ["arm.pick", "arm.place"]
    _untouched(ctx)


def test_execute_task_stops_at_the_first_refusal(fixtures_dir, gateway_env, monkeypatch):
    plan = Plan(
        steps=(
            PlanStep(capability="arm.pick", args={}, confidence=0.99),
            PlanStep(capability="arm.place", args={}, confidence=0.99),
        ),
        raw_response={},
    )
    monkeypatch.setattr(execute_task_module, "decompose", lambda **kw: plan)
    gateway_env.deny("tool_allowlist", "tool arm.pick not in operator allowlist")
    r = execute_task_tool(_ctx(fixtures_dir), prompt="put the lego in the bowl")
    assert r["status"] == "denied"
    assert len(gateway_env.requests) == 1, "a step was sent after the gateway refused one"


def _registry_returning(monkeypatch, backend) -> None:
    class _Registry:
        def resolve(self, spec):
            return {"feetech": backend, "depthai": backend}

    from robot_md.backends import registry as registry_module

    monkeypatch.setattr(
        registry_module.BackendRegistry, "from_entry_points", classmethod(lambda cls: _Registry())
    )


def test_load_context_opens_no_device_by_default(fixtures_dir, monkeypatch):
    """The MCP server never opens the servo bus: where the gateway holds the
    port, opening it here would race the gateway for it. By default it opens
    no camera either, since the gateway's camera actuator may hold that."""
    backend = _RecordingBackend()
    _registry_returning(monkeypatch, backend)
    ctx = load_context(fixtures_dir / MANIFEST)
    assert backend.opened == []
    assert ctx.backend is backend  # resolved for its metadata, not opened


def test_load_context_opens_cameras_only_when_asked(fixtures_dir, monkeypatch):
    from robot_md.mcp.context import ENV_OPEN_CAMERA

    backend = _RecordingBackend()
    _registry_returning(monkeypatch, backend)
    monkeypatch.setenv(ENV_OPEN_CAMERA, "1")
    load_context(fixtures_dir / MANIFEST)
    assert backend.opened == ["open_perception"]


def test_load_context_opens_the_bus_only_when_a_cli_asks(fixtures_dir, monkeypatch):
    """`robot-md pose teach` (a person at the machine) still opens the bus."""
    backend = _RecordingBackend()
    _registry_returning(monkeypatch, backend)
    load_context(fixtures_dir / MANIFEST, open_servo_bus=True)
    assert backend.opened == ["open"]


def test_the_mcp_entry_point_opens_no_device(fixtures_dir, monkeypatch):
    """`robot-md mcp` → server.main → load_context, with no open_servo_bus."""
    from robot_md.mcp import server as server_module

    class _Server:
        def run(self) -> None:
            pass

    backend = _RecordingBackend()
    _registry_returning(monkeypatch, backend)
    monkeypatch.setattr(server_module.sys, "argv", ["robot-md-mcp", str(fixtures_dir / MANIFEST)])
    built: list = []
    monkeypatch.setattr(server_module, "build_server", lambda ctx: built.append(ctx) or _Server())
    assert server_module.main() == 0
    assert backend.opened == []
    assert built and built[0].backend is backend


def test_feetech_depthai_open_perception_leaves_the_servo_bus_closed(fixtures_dir, monkeypatch):
    from robot_md.backends.feetech_depthai import FeetechDepthaiBackend
    from robot_md.backends.feetech_depthai import perception as perception_module
    from robot_md.backends.feetech_depthai import servo as servo_module

    def _no_bus(self):
        pytest.fail("the MCP server opened the servo bus")

    class _Camera:
        opened = False

        def open(self):
            self.opened = True

    camera = _Camera()
    monkeypatch.setattr(servo_module.ServoBus, "open", _no_bus)
    monkeypatch.setattr(
        perception_module.Perception, "from_spec", classmethod(lambda cls, spec: camera)
    )
    spec = RobotSpec.from_parsed(load_context(fixtures_dir / MANIFEST).parsed)
    backend = FeetechDepthaiBackend()
    backend.open_perception(spec)
    assert backend._servo_bus is None
    assert backend._motion is None
    assert backend._perception is camera and camera.opened


async def test_discover_probe_direction_refuses_and_never_writes(fixtures_dir):
    """probe_direction moved a joint by writing the bus. It now refuses."""
    import numpy as np

    from robot_md.mcp.tools.discover import discover_tool

    ctx = _ctx(fixtures_dir)

    class _Cam:
        def grab_frame(self):
            return (np.zeros((4, 4, 3), dtype=np.uint8), np.zeros((4, 4)), np.eye(3))

    ctx.backend._perception = _Cam()
    r = await discover_tool(
        ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}]
    )
    probe = r["results"]["probe_direction"]
    assert probe["status"] == "refused"
    assert "gateway" in probe["message"]
    _untouched(ctx)


# --------------------------------------------------------------------------
# 2. Refusal with no gateway
# --------------------------------------------------------------------------


def test_motion_refuses_with_no_gateway_configured(fixtures_dir):
    ctx = _ctx(fixtures_dir)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "gateway_not_configured"
    assert "install-gateway" in r["error"]["message"]
    _untouched(ctx)


def test_motion_refuses_when_nothing_answers_at_the_gateway_address(
    fixtures_dir, monkeypatch, tmp_path
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(gateway_client.ENV_URL, f"http://127.0.0.1:{_free_port()}")
    monkeypatch.setenv(gateway_client.ENV_BEARER, TEST_BEARER)
    monkeypatch.setenv(gateway_client.ENV_RURI, TEST_RURI)
    ctx = _ctx(fixtures_dir)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "gateway_unreachable"
    _untouched(ctx)


def test_a_dry_run_also_refuses_with_no_gateway_configured(fixtures_dir):
    ctx = _ctx(fixtures_dir)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=True)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "gateway_not_configured"
    _untouched(ctx)


def test_execute_task_refuses_before_planning_with_no_gateway(fixtures_dir, monkeypatch):
    planned: list[int] = []
    monkeypatch.setattr(execute_task_module, "decompose", lambda **kw: planned.append(1))
    r = execute_task_tool(_ctx(fixtures_dir), prompt="pick up the lego")
    assert r["status"] == "error"
    assert r["error"]["reason"] == "gateway_not_configured"
    assert planned == [], "the planner ran although nothing could execute its plan"


def test_a_bearers_file_with_only_a_commission_entry_is_not_used(
    fixtures_dir, monkeypatch, tmp_path
):
    """The server reads the `actuate` entry and nothing else. The commission
    bearer clears stops; it stays with the person at the machine."""
    bearers = tmp_path / "bearers.yaml"
    bearers.write_text(
        "bearers:\n  - {token: commission-secret, tier: commission, caller: person}\n"
    )
    monkeypatch.setenv(gateway_client.ENV_BEARERS_FILE, str(bearers))
    monkeypatch.setenv(gateway_client.ENV_RURI, TEST_RURI)
    r = execute_capability_tool(_ctx(fixtures_dir), capability="arm.pick", args={}, dry_run=False)
    assert r["error"]["reason"] == "gateway_not_configured"
    assert "commission-secret" not in json.dumps(r)


# --------------------------------------------------------------------------
# 3. The envelope the gateway receives
# --------------------------------------------------------------------------


def test_motion_is_one_envelope_to_v1_invoke(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir)
    execute_capability_tool(ctx, capability="arm.pick", args={"target": "red_lego"}, dry_run=False)
    (request,) = gateway_env.requests
    assert request["method"] == "POST"
    assert request["path"] == "/v1/invoke"
    assert request["headers"]["authorization"] == f"Bearer {TEST_BEARER}"
    body = request["body"]
    assert body["type"] == "rcan/v1/invoke"
    assert body["tool_name"] == "arm.pick"
    assert body["tool_args"] == {"target": "red_lego"}
    assert body["scope"] == "ACTUATE"
    assert body["ruri"] == TEST_RURI
    assert body["manifest_path"] == str((fixtures_dir / MANIFEST).resolve())
    assert body["msg_id"] and body["nonce"]
    assert isinstance(body["timestamp_ms"], int)
    assert set(body) <= ENVELOPE_KEYS
    assert not set(body) & HUMAN_CLAIM_KEYS
    assert "actuator_name" not in body


def test_a_read_only_capability_is_sent_as_observe(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir, extra_caps=("status.report",))
    r = execute_capability_tool(ctx, capability="status.report", args={}, dry_run=False)
    assert r["status"] == "ok"
    assert gateway_env.bodies[0]["scope"] == "OBSERVE"


def test_the_actuator_is_named_when_configured(fixtures_dir, gateway_env, monkeypatch):
    monkeypatch.setenv(gateway_client.ENV_ACTUATOR, "so-arm101")
    execute_capability_tool(_ctx(fixtures_dir), capability="arm.pick", args={}, dry_run=False)
    assert gateway_env.bodies[0]["actuator_name"] == "so-arm101"


def test_the_envelope_is_signed_when_the_robot_has_a_keypair(fixtures_dir, gateway_env):
    from robot_md.signing import generate_keypair, save_keypair

    rrn = "RRN-000000000099"
    keypair = generate_keypair()
    save_keypair(rrn, keypair)  # under HOME=tmp_path (gateway_env)
    execute_capability_tool(
        _ctx(fixtures_dir, rrn=rrn), capability="arm.pick", args={}, dry_run=False
    )
    body = gateway_env.bodies[0]
    signature = body["envelope_signature"]
    assert signature["kid"] == keypair.pq_kid
    pre_image = dict(body)
    pre_image["envelope_signature"] = {"kid": signature["kid"], "sig": ""}
    public = ed25519.Ed25519PublicKey.from_public_bytes(keypair.ed25519_pub)
    public.verify(
        base64.b64decode(signature["sig"]),
        canonical_json(pre_image, exclude="envelope_signature"),
    )


def test_the_gateway_pin_and_bearers_file_from_install_gateway_are_used(
    fixtures_dir, fake_gateway, monkeypatch, tmp_path
):
    """With no environment set, the server uses what `robot-md install-gateway`
    wrote: the manifest the gateway pins and the actuate-tier bearer."""
    pinned = tmp_path / "etc" / "ROBOT.md"
    bearers = tmp_path / "etc" / "bearers.yaml"
    bearers.parent.mkdir()
    bearers.write_text(
        "bearers:\n"
        "  - {token: commission-secret, tier: commission, caller: person}\n"
        "  - {token: actuate-from-file, tier: actuate, caller: agent-host}\n"
    )
    env_file = tmp_path / "etc" / "gateway.env"
    env_file.write_text(f"ROBOT_MD_PATH={pinned}\nROBOT_MD_BEARERS_FILE={bearers}\n")
    monkeypatch.setattr(gateway_client, "INSTALL_GATEWAY_ENV_FILE", env_file)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(gateway_client.ENV_URL, fake_gateway.url)
    monkeypatch.setenv(gateway_client.ENV_RURI, TEST_RURI)
    r = execute_capability_tool(_ctx(fixtures_dir), capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "ok", r
    (request,) = fake_gateway.requests
    assert request["headers"]["authorization"] == "Bearer actuate-from-file"
    assert request["body"]["manifest_path"] == str(pinned)


def test_gateway_answers_are_reported_as_given(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir)

    gateway_env.deny(
        "actuator_policy",
        "out_of_workspace: x=500mm is outside the declared workspace",
        telemetry={"deny": "out_of_workspace"},
    )
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "denied"
    assert r["error"]["deny"] == "actuator_policy"
    assert r["error"]["telemetry"] == {"deny": "out_of_workspace"}

    gateway_env.respond(
        500, {"detail": {"actuator_error": "bus timeout", "actuator_error_kind": "OSError"}}
    )
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "actuator_error"

    gateway_env.respond(401, {"detail": "missing Authorization header"})
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["error"]["reason"] == "gateway_auth"

    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "ok"
    assert r["gateway"]["outcome_kind"] == "executed"
    assert r["envelope"]["msg_id"] == gateway_env.bodies[-1]["msg_id"]
    _untouched(ctx)


def test_no_answer_after_sending_is_an_unknown_outcome_not_a_retry(
    fixtures_dir, gateway_env, monkeypatch
):
    monkeypatch.setenv(gateway_client.ENV_TIMEOUT, "0.3")
    release = threading.Event()
    original_allowed = gateway_env.allowed

    def _slow(body):
        release.wait(5)
        return original_allowed(body)

    gateway_env.allowed = _slow
    try:
        r = execute_capability_tool(
            _ctx(fixtures_dir), capability="arm.pick", args={}, dry_run=False
        )
    finally:
        release.set()
    assert r["status"] == "error"
    assert r["error"]["reason"] == "gateway_no_answer"
    assert "do not resend" in r["error"]["message"]
    time.sleep(0.1)
    assert len(gateway_env.requests) == 1, "the request was sent again"


def test_requests_ignore_proxy_settings(fixtures_dir, gateway_env, monkeypatch):
    """The bearer goes to the gateway address, never to a proxy."""
    dead_proxy = f"http://127.0.0.1:{_free_port()}"
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, dead_proxy)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    r = execute_capability_tool(_ctx(fixtures_dir), capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "ok", r
    assert len(gateway_env.requests) == 1


def test_a_dry_run_sends_nothing_and_shows_the_envelope(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir)
    r = execute_capability_tool(
        ctx, capability="arm.pick", args={"target": "red_lego"}, dry_run=True
    )
    assert r["status"] == "dry_run"
    assert r["dry_run"]["sent"] is False
    assert r["dry_run"]["envelope"]["tool_name"] == "arm.pick"
    assert r["dry_run"]["envelope"]["scope"] == "ACTUATE"
    assert gateway_env.requests == []
    _untouched(ctx)


def test_the_bearer_never_appears_in_a_result(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir)
    results = [execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=True)]
    results.append(execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False))
    gateway_env.deny("tier_policy", "nope")
    results.append(execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False))
    results.append(estop_tool(ctx))
    gateway_env.deny("tier_policy", "scope COMMISSION requires the 'commission' tier")
    results.append(estop_clear_tool(ctx))
    for result in results:
        assert TEST_BEARER not in json.dumps(result, default=str)


# --------------------------------------------------------------------------
# Stops
# --------------------------------------------------------------------------


def test_estop_sends_the_gateways_declared_stop(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir)
    r = estop_tool(ctx)
    assert r["ok"] is True
    assert r["stop"] == "stopped"
    (body,) = gateway_env.bodies
    assert body["tool_name"] == "arm.estop"
    assert body["scope"] == "SAFETY"
    assert not set(body) & HUMAN_CLAIM_KEYS
    assert ctx.estop.is_set(), "this server's own latch must be set too"
    _untouched(ctx)


def test_estop_latches_this_server_even_when_the_stop_is_not_confirmed(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir)
    gateway_env.respond(
        500, {"detail": {"actuator_error": "bus timeout", "actuator_error_kind": "OSError"}}
    )
    r = estop_tool(ctx)
    assert r["ok"] is False
    assert r["stop"] == "stop_not_confirmed"
    assert "hardware stop" in r["message"]
    assert ctx.estop.is_set()
    # and no motion leaves this server while its latch is set
    m = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert m["status"] == "blocked"
    assert m["error"]["reason"] == "estop_set"
    assert [b["tool_name"] for b in gateway_env.bodies] == ["arm.estop"]


def test_estop_with_no_gateway_is_not_confirmed_and_touches_no_bus(fixtures_dir, monkeypatch):
    monkeypatch.setenv(gateway_client.ENV_URL, f"http://127.0.0.1:{_free_port()}")
    ctx = _ctx(fixtures_dir)
    r = estop_tool(ctx)
    assert r["ok"] is False
    assert r["stop"] == "stop_not_confirmed"
    assert ctx.estop.is_set()
    _untouched(ctx)


def test_estop_clear_goes_to_the_gateway_at_commission(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir)
    estop_tool(ctx)
    gateway_env.deny(
        "tier_policy", "scope COMMISSION requires the 'commission' tier, not 'actuate'"
    )
    r = estop_clear_tool(ctx)
    assert r["ok"] is False
    assert r["stop"] == "clear_not_confirmed"
    assert ctx.estop.is_set(), "a refused clear must leave this server latched"
    clear = gateway_env.bodies[-1]
    assert clear["tool_name"] == "arm.estop.clear"
    assert clear["scope"] == "COMMISSION"
    assert not set(clear) & HUMAN_CLAIM_KEYS
    # A commission-tier credential the operator chose to give this server:
    r = estop_clear_tool(ctx)
    assert r["ok"] is True
    assert r["stop"] == "cleared"
    assert not ctx.estop.is_set()
    _untouched(ctx)


def test_estop_clear_with_no_gateway_refuses_and_keeps_the_latch(fixtures_dir):
    ctx = _ctx(fixtures_dir)
    ctx.estop.set()
    r = estop_clear_tool(ctx)
    assert r["ok"] is False
    assert r["error"]["reason"] == "gateway_not_configured"
    assert ctx.estop.is_set()


# --------------------------------------------------------------------------
# 4. confirm_token authorizes nothing
# --------------------------------------------------------------------------


@pytest.mark.parametrize("fn", [execute_capability_tool, execute_task_tool, estop_clear_tool])
def test_no_tool_function_takes_a_confirm_token(fn):
    assert "confirm_token" not in inspect.signature(fn).parameters


def test_passing_a_confirm_token_is_an_error_not_an_authorization(fixtures_dir, gateway_env):
    with pytest.raises(TypeError):
        execute_capability_tool(  # type: ignore[call-arg]
            _ctx(fixtures_dir), capability="arm.pick", args={}, dry_run=False, confirm_token="yes"
        )
    assert gateway_env.requests == []


async def test_no_mcp_tool_schema_offers_a_confirm_token(fixtures_dir):
    server = build_server(load_context(fixtures_dir / MANIFEST))
    for tool in await server.list_tools():
        properties = (tool.inputSchema or {}).get("properties", {})
        assert "confirm_token" not in properties, f"{tool.name} still takes confirm_token"


def test_a_hitl_gate_blocks_and_nothing_reaches_the_gateway(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir, gates=[{"scope": "arm", "require_auth": True}])
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "hitl_gate"
    assert r["error"]["scope"] == "arm"
    assert "outside" in r["error"]["message"]
    assert gateway_env.requests == []
    _untouched(ctx)


async def test_a_token_in_the_mcp_call_does_not_open_a_hitl_gate(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir, gates=[{"scope": "arm", "require_auth": True}])
    server = build_server(ctx)
    r = await _call(
        server,
        "execute_capability",
        {"capability": "arm.pick", "args": {}, "confirm_token": "yes, I authorize this"},
    )
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "hitl_gate"
    assert gateway_env.requests == []


async def test_a_token_in_the_mcp_call_does_not_reach_the_gateway(fixtures_dir, gateway_env):
    server = build_server(_ctx(fixtures_dir))
    await _call(server, "execute_capability", {"capability": "arm.pick", "args": {}})
    await _call(
        server,
        "execute_capability",
        {"capability": "arm.pick", "args": {}, "confirm_token": "yes, I authorize this"},
    )
    without, with_token = gateway_env.bodies
    assert set(without) == set(with_token)
    assert "authorize" not in json.dumps(with_token)


async def test_a_token_in_the_mcp_call_does_not_clear_a_stop(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir)
    server = build_server(ctx)
    await _call(server, "estop", {})
    gateway_env.deny(
        "tier_policy", "scope COMMISSION requires the 'commission' tier, not 'actuate'"
    )
    with pytest.raises(ToolError):
        await server.call_tool("estop_clear", {"confirm_token": "yes, clear it"})
    assert ctx.estop.is_set()
    assert gateway_env.bodies[-1]["scope"] == "COMMISSION"
    assert "clear it" not in json.dumps(gateway_env.bodies[-1])


async def test_an_unconfirmed_stop_is_an_mcp_error(fixtures_dir, gateway_env):
    """A client that only reads isError (the pendant does) must not be told a
    stop landed when it did not."""
    server = build_server(_ctx(fixtures_dir))
    gateway_env.respond(
        500, {"detail": {"actuator_error": "bus timeout", "actuator_error_kind": "OSError"}}
    )
    with pytest.raises(ToolError, match="stop_not_confirmed"):
        await server.call_tool("estop", {})


async def test_a_stop_is_not_queued_behind_a_motion_in_flight(fixtures_dir, gateway_env):
    """FastMCP runs a sync tool on the event loop, so a stop sent while a
    motion waited on the gateway used to wait for that motion's answer. The
    motion and stop tools run in worker threads: the stop reaches the gateway
    while the motion is still in flight."""
    import asyncio

    release = threading.Event()
    original_allowed = gateway_env.allowed

    def _slow_motion(body):
        if body.get("tool_name") == "arm.pick":
            release.wait(10)
        return original_allowed(body)

    gateway_env.allowed = _slow_motion
    server = build_server(_ctx(fixtures_dir))
    motion = asyncio.create_task(_call(server, "execute_capability", {"capability": "arm.pick"}))
    try:
        for _ in range(100):  # wait until the motion request is at the gateway
            if gateway_env.requests:
                break
            await asyncio.sleep(0.02)
        stop = await asyncio.wait_for(_call(server, "estop", {}), timeout=5)
        assert stop["stop"] == "stopped"
        assert not motion.done(), "the motion finished first; the test proves nothing"
        assert [b["tool_name"] for b in gateway_env.bodies] == ["arm.pick", "arm.estop"]
    finally:
        release.set()
    assert (await motion)["status"] == "ok"


def test_a_stop_set_while_a_motion_is_prepared_withholds_it(fixtures_dir, gateway_env, monkeypatch):
    """In worker threads, a stop can land after a motion passed the first
    latch check. The latch is checked again after the envelope is built and
    signed, just before the request is sent, so that motion is not sent."""
    ctx = _ctx(fixtures_dir)
    original = gateway_client.prepare_envelope

    def _stop_lands_meanwhile(*args, **kwargs):
        ctx.estop.set()  # what the estop tool does, from another thread
        return original(*args, **kwargs)

    monkeypatch.setattr(gateway_client, "prepare_envelope", _stop_lands_meanwhile)
    result = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert result["status"] == "blocked"
    assert result["error"]["reason"] == "estop_set"
    assert gateway_env.requests == []
    _untouched(ctx)


def test_a_read_prepared_across_a_stop_is_still_sent(fixtures_dir, gateway_env, monkeypatch):
    """Reads pass the latch, before and after: the state stays readable."""
    ctx = _ctx(fixtures_dir, extra_caps=("status.report",))
    original = gateway_client.prepare_envelope

    def _stop_lands_meanwhile(*args, **kwargs):
        ctx.estop.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(gateway_client, "prepare_envelope", _stop_lands_meanwhile)
    result = execute_capability_tool(ctx, capability="status.report", args={}, dry_run=False)
    assert result["status"] == "ok"
    assert [b["tool_name"] for b in gateway_env.bodies] == ["status.report"]
