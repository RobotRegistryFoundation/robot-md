"""Unit tests for execute_capability MCP tool."""

from __future__ import annotations

from robot_md.backends.base import CapabilityBackend, ExecutionEvent, ExecutionResult
from robot_md.mcp.context import load_context
from robot_md.mcp.tools.execute_capability import execute_capability_tool


class _PickOnly(CapabilityBackend):
    name = "pickonly"
    protocols = frozenset({"feetech", "depthai"})

    def open(self, spec):
        self.spec = spec

    def close(self):
        pass

    def capabilities(self):
        return frozenset({"arm.pick", "arm.place"})

    def execute(self, capability, args, *, dry_run, estop):
        return ExecutionResult(
            status="ok",
            trajectory=[{"joint": "shoulder_pan", "target": 0.0}],
            events=[ExecutionEvent(kind="done", data={})],
            error=None,
        )


def test_execute_capability_rejects_undeclared_capability(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = _PickOnly()
    ctx.backend.open(ctx.spec)
    r = execute_capability_tool(
        ctx, capability="arm.throw", args={}, dry_run=False, confirm_token=None
    )
    assert r["status"] == "error"
    assert r["error"]["reason"] == "not_declared"


def test_execute_capability_rejects_not_implemented(fixtures_dir):
    """Capability declared in spec but not implemented by backend → not_implemented."""
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    # Add arm.reach to spec but backend only implements arm.pick/arm.place
    ctx.parsed.frontmatter["capabilities"].append("arm.reach")
    from robot_md.robot_spec import RobotSpec

    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.backend = _PickOnly()
    ctx.backend.open(ctx.spec)
    r = execute_capability_tool(
        ctx, capability="arm.reach", args={}, dry_run=False, confirm_token=None
    )
    assert r["status"] == "error"
    assert r["error"]["reason"] == "not_implemented"


def test_execute_capability_returns_trajectory(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = _PickOnly()
    ctx.backend.open(ctx.spec)
    r = execute_capability_tool(
        ctx, capability="arm.pick", args={"object": "lego"}, dry_run=True, confirm_token=None
    )
    assert r["status"] == "ok"
    assert r["trajectory"] == [{"joint": "shoulder_pan", "target": 0.0}]


def test_execute_capability_blocks_on_estop(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = _PickOnly()
    ctx.backend.open(ctx.spec)
    ctx.estop.set()
    r = execute_capability_tool(
        ctx, capability="arm.pick", args={}, dry_run=False, confirm_token=None
    )
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "estop_set"


def test_execute_capability_returns_no_backend_when_unresolved(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = None
    r = execute_capability_tool(
        ctx, capability="arm.pick", args={}, dry_run=False, confirm_token=None
    )
    assert r["status"] == "error"
    assert r["error"]["reason"] == "no_backend"


def test_execute_capability_hitl_gate_blocks_without_token(fixtures_dir):
    """When spec declares an hitl_gate matching the capability scope, execute blocks
    until a confirm_token is supplied."""
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    # Add an hitl_gate for scope "arm"
    ctx.parsed.frontmatter["safety"].setdefault("hitl_gates", []).append(
        {"scope": "arm", "require_auth": True}
    )
    from robot_md.robot_spec import RobotSpec

    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.backend = _PickOnly()
    ctx.backend.open(ctx.spec)

    r = execute_capability_tool(
        ctx, capability="arm.pick", args={}, dry_run=False, confirm_token=None
    )
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "hitl_gate"

    r2 = execute_capability_tool(
        ctx, capability="arm.pick", args={}, dry_run=False, confirm_token="anything"
    )
    assert r2["status"] == "ok"
