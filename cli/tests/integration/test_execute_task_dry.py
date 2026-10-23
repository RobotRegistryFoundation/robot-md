"""End-to-end execute_task with a fake planner client and a fake gateway.

Every step goes to robot-md-gateway (tests.fake_gateway.FakeGateway); the
in-process backend only supplies the scene and must never execute.
"""

from __future__ import annotations

import pytest

from robot_md.backends.base import CapabilityBackend, SceneSnapshot
from robot_md.mcp.context import load_context
from robot_md.mcp.tools.execute_task import execute_task_tool
from robot_md.robot_spec import RobotSpec

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

    def scene_describe(self):
        return SceneSnapshot.empty()


def _ctx_with_planner(fixtures_dir, confidence_gate: float):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.parsed.frontmatter["brain"] = {
        "planning": {
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "confidence_gate": confidence_gate,
        }
    }
    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.backend = _Fake()
    return ctx


def _planner_returning(monkeypatch, plan: list[dict]) -> None:
    monkeypatch.setattr(
        "robot_md.planning.decompose._build_default_client",
        lambda provider: lambda prompt, model, timeout_ms: {"plan": plan},
    )


def test_execute_task_dry_run_decomposes_and_sends_nothing(fixtures_dir, monkeypatch, gateway_env):
    ctx = _ctx_with_planner(fixtures_dir, 0.6)
    _planner_returning(
        monkeypatch,
        [
            {"capability": "arm.pick", "args": {"object": "lego"}, "confidence": 0.9},
            {"capability": "arm.place", "args": {"pose": {"x": -0.1}}, "confidence": 0.8},
        ],
    )
    r = execute_task_tool(ctx, prompt="pick the lego and place it left", dry_run=True)
    assert r["status"] == "dry_run"
    assert [s["capability"] for s in r["plan"]] == ["arm.pick", "arm.place"]
    assert len(r["executions"]) == 2
    assert [e["dry_run"]["envelope"]["tool_name"] for e in r["executions"]] == [
        "arm.pick",
        "arm.place",
    ]
    assert gateway_env.requests == []


def test_execute_task_runs_each_step_through_the_gateway(fixtures_dir, monkeypatch, gateway_env):
    ctx = _ctx_with_planner(fixtures_dir, 0.6)
    _planner_returning(
        monkeypatch,
        [
            {"capability": "arm.pick", "args": {"object": "lego"}, "confidence": 0.9},
            {"capability": "arm.place", "args": {"pose": {"x": -0.1}}, "confidence": 0.8},
        ],
    )
    r = execute_task_tool(ctx, prompt="pick the lego and place it left")
    assert r["status"] == "ok"
    assert [b["tool_name"] for b in gateway_env.bodies] == ["arm.pick", "arm.place"]


def test_execute_task_low_confidence_returns_blocked(fixtures_dir, monkeypatch, gateway_env):
    ctx = _ctx_with_planner(fixtures_dir, 0.8)
    _planner_returning(monkeypatch, [{"capability": "arm.pick", "args": {}, "confidence": 0.5}])
    r = execute_task_tool(ctx, prompt="x", dry_run=True)
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "low_confidence"
    assert gateway_env.requests == []


def test_execute_task_no_planner_declared(fixtures_dir, gateway_env):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    # NO brain block
    ctx.backend = _Fake()
    r = execute_task_tool(ctx, prompt="x", dry_run=True)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "no_planner_declared"


def test_execute_task_aborts_on_step_refusal(fixtures_dir, monkeypatch, gateway_env):
    """If the gateway does not run the first step, the rest are not sent."""
    ctx = _ctx_with_planner(fixtures_dir, 0.6)
    _planner_returning(
        monkeypatch,
        [
            {"capability": "arm.pick", "args": {}, "confidence": 0.9},
            {"capability": "arm.place", "args": {}, "confidence": 0.9},
        ],
    )
    gateway_env.respond(
        500, {"detail": {"actuator_error": "fake_fail", "actuator_error_kind": "X"}}
    )
    r = execute_task_tool(ctx, prompt="x")
    # arm.pick fails → arm.place is not sent
    assert len(r["executions"]) == 1
    assert r["executions"][0]["status"] == "error"
    assert r["status"] == "error"
    assert [b["tool_name"] for b in gateway_env.bodies] == ["arm.pick"]
