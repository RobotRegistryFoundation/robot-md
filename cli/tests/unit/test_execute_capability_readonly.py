from __future__ import annotations

from robot_md.backends.base import CapabilityBackend, ExecutionResult
from robot_md.mcp.context import load_context
from robot_md.mcp.tools.execute_capability import execute_capability_tool
from robot_md.robot_spec import RobotSpec


class _ReadOnly(CapabilityBackend):
    name = "readonly-stub"
    protocols = frozenset({"feetech", "depthai"})
    read_only_capabilities = frozenset({"status.report"})

    def open(self, spec): self.spec = spec
    def close(self): pass
    def capabilities(self): return frozenset({"arm.pick", "status.report"})
    def execute(self, capability, args, *, dry_run, estop):
        return ExecutionResult(status="ok", trajectory=None, events=[], error=None)


def test_estop_set_blocks_motion_capability(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = _ReadOnly(); ctx.backend.open(ctx.spec)
    ctx.estop.set()
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False, confirm_token=None)
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "estop_set"


def test_estop_set_does_not_block_read_only_capability(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    # Add status.report to spec's declared capabilities so it can be executed
    ctx.parsed.frontmatter["capabilities"].append("status.report")
    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.backend = _ReadOnly(); ctx.backend.open(ctx.spec)
    ctx.estop.set()
    r = execute_capability_tool(ctx, capability="status.report", args={}, dry_run=False, confirm_token=None)
    assert r["status"] == "ok", f"read-only capability blocked by estop: {r}"


def test_backend_without_read_only_set_still_blocks_all(fixtures_dir):
    """Backwards compat: backends that don't declare read_only_capabilities keep old behavior."""
    class _Legacy(CapabilityBackend):
        name = "legacy"
        protocols = frozenset({"feetech", "depthai"})
        def open(self, spec): pass
        def close(self): pass
        def capabilities(self): return frozenset({"status.report"})
        def execute(self, capability, args, *, dry_run, estop):
            return ExecutionResult(status="ok", trajectory=None, events=[], error=None)

    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    # Add status.report to spec's declared capabilities so it can be executed
    ctx.parsed.frontmatter["capabilities"].append("status.report")
    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.backend = _Legacy(); ctx.backend.open(ctx.spec)
    ctx.estop.set()
    r = execute_capability_tool(ctx, capability="status.report", args={}, dry_run=False, confirm_token=None)
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "estop_set"
