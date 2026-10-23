from __future__ import annotations

import json
import time
from pathlib import Path

from robot_md.mcp.context import load_context


def test_publisher_wired_by_default(fixtures_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("ROBOT_MD_DASHBOARD_DISABLED", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    try:
        assert ctx.publisher is not None
        expected = tmp_path / ".robot-md" / "events.jsonl"
        assert Path(ctx.publisher.jsonl_path) == expected
    finally:
        if ctx.publisher:
            ctx.publisher.stop()


def test_publisher_disabled_by_env(fixtures_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ROBOT_MD_DASHBOARD_DISABLED", "1")
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    assert ctx.publisher is None
    assert ctx._command_watcher is None


def _write_cmd(tmp_path: Path, cmd: str) -> None:
    cmd_path = tmp_path / ".robot-md" / "commands.jsonl"
    cmd_path.parent.mkdir(exist_ok=True)
    with cmd_path.open("a") as f:
        f.write(json.dumps({"cmd": cmd, "ts": time.time()}) + "\n")
        f.flush()


def _wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline and not predicate():
        time.sleep(0.05)


def test_command_watcher_estop_set_latches_and_sends_the_gateway_stop(
    fixtures_dir, tmp_path, monkeypatch, gateway_env
):
    """The dashboard's stop takes the MCP estop path: this server latches, and
    the gateway's declared stop is sent."""
    monkeypatch.delenv("ROBOT_MD_DASHBOARD_DISABLED", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    try:
        _write_cmd(tmp_path, "estop.set")
        _wait_for(lambda: ctx.estop.is_set() and gateway_env.requests)
        assert ctx.estop.is_set()
        assert [b["tool_name"] for b in gateway_env.bodies] == ["arm.estop"]
    finally:
        if ctx.publisher:
            ctx.publisher.stop()


def test_command_watcher_estop_clear_asks_the_gateway(
    fixtures_dir, tmp_path, monkeypatch, gateway_env
):
    """The dashboard's clear is not an in-process clear: it asks the gateway at
    the commission tier, and the latch follows the gateway's answer."""
    monkeypatch.delenv("ROBOT_MD_DASHBOARD_DISABLED", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    try:
        ctx.estop.set()
        _write_cmd(tmp_path, "estop.clear")
        _wait_for(lambda: not ctx.estop.is_set())
        assert not ctx.estop.is_set()
        assert gateway_env.bodies[-1]["tool_name"] == "arm.estop.clear"
        assert gateway_env.bodies[-1]["scope"] == "COMMISSION"
    finally:
        if ctx.publisher:
            ctx.publisher.stop()


def test_command_watcher_estop_clear_refused_keeps_the_latch(
    fixtures_dir, tmp_path, monkeypatch, gateway_env
):
    monkeypatch.delenv("ROBOT_MD_DASHBOARD_DISABLED", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    try:
        ctx.estop.set()
        gateway_env.deny("tier_policy", "scope COMMISSION requires the 'commission' tier")
        _write_cmd(tmp_path, "estop.clear")
        _wait_for(lambda: bool(gateway_env.requests))
        time.sleep(0.3)
        assert ctx.estop.is_set()
    finally:
        if ctx.publisher:
            ctx.publisher.stop()


def test_command_watcher_ignores_unknown_cmd(fixtures_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("ROBOT_MD_DASHBOARD_DISABLED", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    try:
        cmd_path = tmp_path / ".robot-md" / "commands.jsonl"
        cmd_path.parent.mkdir(exist_ok=True)
        with cmd_path.open("a") as f:
            f.write(json.dumps({"cmd": "bogus.thing"}) + "\n")
        time.sleep(0.5)
        # Unknown command is logged but doesn't crash; ctx stays consistent.
        assert not ctx.estop.is_set()
    finally:
        if ctx.publisher:
            ctx.publisher.stop()


def test_execute_capability_publishes_call_and_result(fixtures_dir, tmp_path, monkeypatch):
    """execute_capability_tool emits tool.call + tool.result events."""
    monkeypatch.delenv("ROBOT_MD_DASHBOARD_DISABLED", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    try:
        from robot_md.backends.base import CapabilityBackend, ExecutionResult
        from robot_md.mcp.tools.execute_capability import execute_capability_tool

        class _Fake(CapabilityBackend):
            name = "fake"
            protocols = frozenset({"feetech", "depthai"})

            def open(self, spec):
                self.spec = spec

            def close(self):
                pass

            def capabilities(self):
                return frozenset({"arm.pick"})

            def execute(self, capability, args, *, dry_run, estop):
                return ExecutionResult(status="ok", trajectory=None, events=[], error=None)

        ctx.backend = _Fake()
        ctx.backend.open(ctx.spec)
        execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=True)
        time.sleep(0.3)

        events_path = tmp_path / ".robot-md" / "events.jsonl"
        lines = events_path.read_text().splitlines()
        kinds = [json.loads(line)["kind"] for line in lines]
        assert "tool.call" in kinds
        assert "tool.result" in kinds
    finally:
        if ctx.publisher:
            ctx.publisher.stop()
