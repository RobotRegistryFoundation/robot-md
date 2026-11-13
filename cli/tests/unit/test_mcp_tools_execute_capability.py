"""Unit tests for execute_capability MCP tool.

execute_capability is a client of robot-md-gateway: it never calls the
backend. The tests for that contract are in
test_mcp_motion_through_gateway.py; these cover the checks it makes before
anything is sent, and what it publishes.
"""

from __future__ import annotations

from robot_md.backends.base import CapabilityBackend, ExecutionEvent, ExecutionResult
from robot_md.mcp.context import load_context
from robot_md.mcp.tools.execute_capability import execute_capability_tool


class _PickOnly(CapabilityBackend):
    name = "pickonly"
    protocols = frozenset({"feetech", "depthai"})

    def __init__(self) -> None:
        self.executed: list[str] = []

    def open(self, spec):
        self.spec = spec

    def close(self):
        pass

    def capabilities(self):
        return frozenset({"arm.pick", "arm.place"})

    def execute(self, capability, args, *, dry_run, estop):
        self.executed.append(capability)
        return ExecutionResult(
            status="ok",
            trajectory=[{"joint": "shoulder_pan", "target": 0.0}],
            events=[ExecutionEvent(kind="done", data={})],
            error=None,
        )


def test_execute_capability_rejects_undeclared_capability(fixtures_dir, gateway_env):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = _PickOnly()
    r = execute_capability_tool(ctx, capability="arm.throw", args={}, dry_run=False)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "not_declared"
    assert gateway_env.requests == []


def test_a_capability_the_local_backend_lacks_still_goes_to_the_gateway(fixtures_dir, gateway_env):
    """Whether a capability is implemented is the gateway's actuator's answer,
    not the in-process backend's (which no longer executes anything)."""
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.parsed.frontmatter["capabilities"].append("arm.reach")
    from robot_md.robot_spec import RobotSpec

    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.backend = _PickOnly()
    gateway_env.deny("tool_allowlist", "tool arm.reach not in operator allowlist")
    r = execute_capability_tool(ctx, capability="arm.reach", args={}, dry_run=False)
    assert r["status"] == "denied"
    assert r["error"]["deny"] == "tool_allowlist"
    assert gateway_env.bodies[0]["tool_name"] == "arm.reach"
    assert ctx.backend.executed == []


def test_execute_capability_returns_the_gateways_answer(fixtures_dir, gateway_env):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = _PickOnly()
    r = execute_capability_tool(ctx, capability="arm.pick", args={"object": "lego"}, dry_run=False)
    assert r["status"] == "ok"
    assert r["gateway"]["outcome_kind"] == "executed"
    assert r["trajectory"] is None
    assert ctx.backend.executed == []


def test_execute_capability_blocks_on_estop(fixtures_dir, gateway_env):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = _PickOnly()
    ctx.estop.set()
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "estop_set"
    assert gateway_env.requests == []


def test_execute_capability_refuses_without_a_gateway(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = None
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "gateway_not_configured"


def test_execute_capability_hitl_gate_blocks_and_no_token_exists_to_open_it(
    fixtures_dir, gateway_env
):
    """A gate that requires authorization blocks MCP motion. The token that
    used to open it was written by the model; there is no such parameter now."""
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.parsed.frontmatter["safety"].setdefault("hitl_gates", []).append(
        {"scope": "arm", "require_auth": True}
    )
    from robot_md.robot_spec import RobotSpec

    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.backend = _PickOnly()

    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "hitl_gate"
    assert gateway_env.requests == []


def test_a_gate_that_does_not_require_auth_does_not_block(fixtures_dir, gateway_env):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.parsed.frontmatter["safety"].setdefault("hitl_gates", []).append(
        {"scope": "arm", "require_auth": False}
    )
    from robot_md.robot_spec import RobotSpec

    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "ok"


def test_execute_capability_precondition_failure_returns_structured(fixtures_dir, gateway_env):
    """When a declared capability has a precondition that fails, the error
    shape is {reason: 'precondition', preconditions: list[dict]} with each
    entry carrying kind/name/message/suggested_fix."""
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = _PickOnly()

    # Inject a capability contract that requires the extrinsic to be present.
    # The fixture manifest doesn't have an extrinsic set (preset_default), so
    # this should fail the extrinsic_present precondition.
    from robot_md.robot_spec import CapabilityContract, Precondition

    ctx.spec.capability_contracts["arm.pick"] = CapabilityContract(
        preconditions=(Precondition(kind="extrinsic_present", name=None, detail={}),)
    )
    # Ensure no camera has an extrinsic set so the precondition trips.
    for cam in ctx.spec.physics.cameras:
        object.__setattr__(cam, "extrinsic", None)

    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "precondition"
    assert "preconditions" in r["error"]
    assert "failed" not in r["error"]
    assert len(r["error"]["preconditions"]) == 1
    pc = r["error"]["preconditions"][0]
    assert pc["kind"] == "extrinsic_present"
    assert pc["suggested_fix"] == "robot-md calibrate --extrinsic"
    assert pc["message"] == "hand-eye extrinsic missing"
    assert gateway_env.requests == []


def test_execute_capability_publishes_error_on_tool_result(fixtures_dir, tmp_path, monkeypatch):
    """_publish_result must forward the error field so InvocationRecord can
    read reason/preconditions during live-pair or JSONL backfill."""
    # Enable the dashboard publisher (unit conftest disables it by default)
    # and steer HOME to a tmp dir so events.jsonl is isolated.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ROBOT_MD_DASHBOARD_DISABLED", "0")

    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = _PickOnly()

    # Capture what the publisher saw.
    published: list[tuple[str, dict]] = []
    inner = getattr(ctx.publisher, "_inner", ctx.publisher)
    orig_publish = inner.publish

    def _capture(kind, data):
        published.append((kind, dict(data)))
        return orig_publish(kind, data)

    inner.publish = _capture

    r = execute_capability_tool(ctx, capability="arm.throw", args={}, dry_run=False)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "not_declared"

    results = [(k, d) for k, d in published if k == "tool.result"]
    assert len(results) == 1
    _kind, data = results[0]
    assert data["status"] == "error"
    assert data["error"] is not None
    assert data["error"]["reason"] == "not_declared"


def test_execute_capability_refusal_without_gateway_still_publishes(
    fixtures_dir, tmp_path, monkeypatch
):
    """A refusal is an observability-visible failure: tool.call + tool.result
    must both reach the publisher so the InvocationLog ring and the JSONL
    backfill path capture the invocation. Without this the agent has no way
    to answer 'why did my last pick fail?' when no gateway is set up."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ROBOT_MD_DASHBOARD_DISABLED", "0")

    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = None

    published: list[tuple[str, dict]] = []
    inner = getattr(ctx.publisher, "_inner", ctx.publisher)
    orig_publish = inner.publish

    def _capture(kind, data):
        published.append((kind, dict(data)))
        return orig_publish(kind, data)

    inner.publish = _capture

    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "gateway_not_configured"

    kinds = [k for k, _ in published]
    assert "tool.call" in kinds, f"expected tool.call, got {kinds}"
    assert "tool.result" in kinds, f"expected tool.result, got {kinds}"

    result_events = [d for k, d in published if k == "tool.result"]
    assert len(result_events) == 1
    assert result_events[0]["error"]["reason"] == "gateway_not_configured"
