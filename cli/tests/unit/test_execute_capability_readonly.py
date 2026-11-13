"""Read-only capabilities pass this server's stop latch; motion does not.

Both go to robot-md-gateway. A read-only capability goes under the OBSERVE
scope, so the state of a stopped robot can still be read; the gateway refuses
a motion tool sent under OBSERVE, so the label cannot move anything.
"""

from __future__ import annotations

from robot_md.backends.base import CapabilityBackend
from robot_md.mcp.context import load_context
from robot_md.mcp.tools.execute_capability import execute_capability_tool
from robot_md.robot_spec import RobotSpec


class _ReadOnly(CapabilityBackend):
    name = "readonly-stub"
    protocols = frozenset({"feetech", "depthai"})
    read_only_capabilities = frozenset({"vendor.peek"})

    def open(self, spec):
        self.spec = spec

    def close(self):
        pass

    def capabilities(self):
        return frozenset({"arm.pick", "status.report", "vendor.peek"})

    def execute(self, capability, args, *, dry_run, estop):
        raise AssertionError("the MCP server must not execute capabilities in-process")


def _ctx(fixtures_dir, *caps):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.parsed.frontmatter["capabilities"].extend(caps)
    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.backend = _ReadOnly()
    return ctx


def test_estop_set_blocks_motion_capability(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir)
    ctx.estop.set()
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "estop_set"
    assert gateway_env.requests == []


def test_estop_set_does_not_block_read_only_capability(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir, "status.report")
    ctx.estop.set()
    r = execute_capability_tool(ctx, capability="status.report", args={}, dry_run=False)
    assert r["status"] == "ok", f"read-only capability blocked by estop: {r}"
    assert gateway_env.bodies[0]["scope"] == "OBSERVE"


def test_a_backend_declared_read_only_capability_is_also_read_only(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir, "vendor.peek")
    ctx.estop.set()
    r = execute_capability_tool(ctx, capability="vendor.peek", args={}, dry_run=False)
    assert r["status"] == "ok"
    assert gateway_env.bodies[0]["scope"] == "OBSERVE"


def test_status_report_is_read_only_with_no_backend(fixtures_dir, gateway_env):
    """The read-only list does not depend on an in-process backend."""
    ctx = _ctx(fixtures_dir, "status.report")
    ctx.backend = None
    ctx.estop.set()
    r = execute_capability_tool(ctx, capability="status.report", args={}, dry_run=False)
    assert r["status"] == "ok"
    assert gateway_env.bodies[0]["scope"] == "OBSERVE"
