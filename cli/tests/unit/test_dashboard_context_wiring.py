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


def test_command_watcher_dispatches_estop_set(fixtures_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("ROBOT_MD_DASHBOARD_DISABLED", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    try:
        cmd_path = tmp_path / ".robot-md" / "commands.jsonl"
        cmd_path.parent.mkdir(exist_ok=True)
        with cmd_path.open("a") as f:
            f.write(json.dumps({"cmd": "estop.set", "ts": time.time()}) + "\n")
            f.flush()
        deadline = time.time() + 3.0
        while time.time() < deadline and not ctx.estop.is_set():
            time.sleep(0.1)
        assert ctx.estop.is_set()
    finally:
        if ctx.publisher:
            ctx.publisher.stop()


def test_command_watcher_dispatches_estop_clear(fixtures_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("ROBOT_MD_DASHBOARD_DISABLED", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    try:
        ctx.estop.set()
        cmd_path = tmp_path / ".robot-md" / "commands.jsonl"
        cmd_path.parent.mkdir(exist_ok=True)
        with cmd_path.open("a") as f:
            f.write(json.dumps({"cmd": "estop.clear", "ts": time.time()}) + "\n")
            f.flush()
        deadline = time.time() + 3.0
        while time.time() < deadline and ctx.estop.is_set():
            time.sleep(0.1)
        assert not ctx.estop.is_set()
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
        execute_capability_tool(
            ctx, capability="arm.pick", args={}, dry_run=True, confirm_token=None
        )
        time.sleep(0.3)

        events_path = tmp_path / ".robot-md" / "events.jsonl"
        lines = events_path.read_text().splitlines()
        kinds = [json.loads(line)["kind"] for line in lines]
        assert "tool.call" in kinds
        assert "tool.result" in kinds
    finally:
        if ctx.publisher:
            ctx.publisher.stop()
