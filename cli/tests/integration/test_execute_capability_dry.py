"""Dry-run execute_capability against a loaded server context."""

from __future__ import annotations

import pytest

from robot_md.backends.base import CapabilityBackend, ExecutionEvent, ExecutionResult
from robot_md.mcp.context import load_context
from robot_md.mcp.tools.execute_capability import execute_capability_tool

pytestmark = pytest.mark.integration


class _Fake(CapabilityBackend):
    name = "fake"
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
            trajectory=[{"joint": "shoulder_pan", "target": 0.5}],
            events=[ExecutionEvent(kind="plan", data={"cap": capability})],
            error=None,
        )


def test_execute_dry_returns_trajectory(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = _Fake()
    ctx.backend.open(ctx.spec)
    r = execute_capability_tool(
        ctx,
        capability="arm.pick",
        args={"object": "lego"},
        dry_run=True,
        confirm_token=None,
    )
    assert r["status"] == "ok"
    assert len(r["trajectory"]) == 1
    assert r["events"] and r["events"][0]["kind"] == "plan"
