"""Dry-run execute_capability against a loaded server context.

A dry run builds the envelope exactly as it would be sent to robot-md-gateway
and sends nothing. The in-process backend is never asked to plan or move.
"""

from __future__ import annotations

import pytest

from robot_md.backends.base import CapabilityBackend
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
        raise AssertionError("the MCP server must not execute capabilities in-process")


def test_execute_dry_returns_the_envelope_and_sends_nothing(fixtures_dir, gateway_env):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.backend = _Fake()
    r = execute_capability_tool(
        ctx,
        capability="arm.pick",
        args={"object": "lego"},
        dry_run=True,
    )
    assert r["status"] == "dry_run"
    preview = r["dry_run"]
    assert preview["sent"] is False
    assert preview["gateway_url"] == gateway_env.url + "/v1/invoke"
    assert preview["envelope"]["tool_args"] == {"object": "lego"}
    assert "envelope_signature" not in preview["envelope"]
    assert gateway_env.requests == []
