"""End-to-end execute_task with a fake planner client."""

from __future__ import annotations

import pytest

from robot_md.backends.base import CapabilityBackend, ExecutionResult, SceneSnapshot
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
        return ExecutionResult(
            status="ok", trajectory=[{"t": 0.0, "joints": {}}], events=[], error=None
        )

    def scene_describe(self):
        return SceneSnapshot.empty()


def test_execute_task_dry_run_decomposes_and_runs(fixtures_dir, monkeypatch):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.parsed.frontmatter["brain"] = {
        "planning": {
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "confidence_gate": 0.6,
        }
    }
    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.backend = _Fake()
    ctx.backend.open(ctx.spec)

    monkeypatch.setattr(
        "robot_md.planning.decompose._build_default_client",
        lambda provider: (
            lambda prompt, model, timeout_ms: {
                "plan": [
                    {
                        "capability": "arm.pick",
                        "args": {"object": "lego"},
                        "confidence": 0.9,
                    },
                    {
                        "capability": "arm.place",
                        "args": {"pose": {"x": -0.1}},
                        "confidence": 0.8,
                    },
                ]
            }
        ),
    )

    r = execute_task_tool(
        ctx, prompt="pick the lego and place it left", dry_run=True, confirm_token=None
    )
    assert r["status"] == "ok"
    assert [s["capability"] for s in r["plan"]] == ["arm.pick", "arm.place"]
    assert len(r["executions"]) == 2


def test_execute_task_low_confidence_returns_blocked(fixtures_dir, monkeypatch):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.parsed.frontmatter["brain"] = {
        "planning": {
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "confidence_gate": 0.8,
        }
    }
    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.backend = _Fake()
    ctx.backend.open(ctx.spec)

    monkeypatch.setattr(
        "robot_md.planning.decompose._build_default_client",
        lambda provider: (
            lambda prompt, model, timeout_ms: {"plan": [
                {"capability": "arm.pick", "args": {}, "confidence": 0.5}
            ]}
        ),
    )

    r = execute_task_tool(ctx, prompt="x", dry_run=True, confirm_token=None)
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "low_confidence"


def test_execute_task_no_planner_declared(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    # NO brain block
    ctx.backend = _Fake()
    ctx.backend.open(ctx.spec)
    r = execute_task_tool(ctx, prompt="x", dry_run=True, confirm_token=None)
    assert r["status"] == "error"
    assert r["error"]["reason"] == "no_planner_declared"


def test_execute_task_aborts_on_step_failure(fixtures_dir, monkeypatch):
    """If the first step returns not-ok, remaining steps are skipped."""

    class _OneFails(CapabilityBackend):
        name = "onefails"
        protocols = frozenset({"feetech", "depthai"})

        def open(self, spec):
            self.spec = spec

        def close(self):
            pass

        def capabilities(self):
            return frozenset({"arm.pick", "arm.place"})

        def execute(self, capability, args, *, dry_run, estop):
            if capability == "arm.pick":
                return ExecutionResult(
                    status="error",
                    trajectory=None,
                    events=[],
                    error={"reason": "fake_fail"},
                )
            return ExecutionResult(
                status="ok", trajectory=None, events=[], error=None
            )

        def scene_describe(self):
            return SceneSnapshot.empty()

    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.parsed.frontmatter["brain"] = {
        "planning": {
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "confidence_gate": 0.6,
        }
    }
    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.backend = _OneFails()
    ctx.backend.open(ctx.spec)

    monkeypatch.setattr(
        "robot_md.planning.decompose._build_default_client",
        lambda provider: (
            lambda prompt, model, timeout_ms: {
                "plan": [
                    {"capability": "arm.pick", "args": {}, "confidence": 0.9},
                    {"capability": "arm.place", "args": {}, "confidence": 0.9},
                ]
            }
        ),
    )

    r = execute_task_tool(ctx, prompt="x", dry_run=True, confirm_token=None)
    # arm.pick fails → arm.place is not executed
    assert len(r["executions"]) == 1
    assert r["executions"][0]["status"] == "error"
    assert r["status"] == "error"
