"""Tests for the publisher-wrapping manifest-stamp + fan-out hook."""
from __future__ import annotations

from pathlib import Path

from robot_md.mcp.context import McpContext, _install_publisher_fanout
from robot_md.mcp.invocation_log import InvocationLog


class _FakePublisher:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def publish(self, kind: str, data: dict) -> None:
        self.events.append((kind, dict(data)))


def _fresh_ctx(tmp_path: Path) -> McpContext:
    manifest = tmp_path / "M.md"
    manifest.write_text("")
    ctx = McpContext(manifest_path=manifest, parsed=None)
    ctx.publisher = _FakePublisher()
    ctx.invocation_log = InvocationLog(maxlen=10)
    _install_publisher_fanout(ctx)
    # ctx.publisher is now the wrapper; ctx.publisher._inner is the _FakePublisher.
    return ctx


def test_wrapper_stamps_manifest_path(tmp_path: Path):
    ctx = _fresh_ctx(tmp_path)
    ctx.publisher.publish("estop.set", {"set": True})
    # Inspect what landed on the underlying publisher via the wrapper's ref.
    underlying = ctx.publisher._inner  # the wrapper exposes its wrapped publisher
    assert underlying.events[0][0] == "estop.set"
    assert underlying.events[0][1]["manifest_path"] == str(ctx.manifest_path)
    assert underlying.events[0][1]["set"] is True


def test_wrapper_does_not_mutate_caller_dict(tmp_path: Path):
    ctx = _fresh_ctx(tmp_path)
    data = {"foo": "bar"}
    ctx.publisher.publish("tool.call", data)
    assert "manifest_path" not in data  # caller's dict untouched


def test_pair_call_and_result_appends_to_log(tmp_path: Path):
    ctx = _fresh_ctx(tmp_path)
    ctx.publisher.publish(
        "tool.call",
        {
            "tool": "execute_capability",
            "capability": "arm.pick",
            "args": {"object": "lego"},
            "dry_run": False,
            "request_id": "r1",
        },
    )
    assert ctx.invocation_log.snapshot() == []  # not yet paired
    ctx.publisher.publish(
        "tool.result",
        {
            "tool": "execute_capability",
            "capability": "arm.pick",
            "status": "ok",
            "request_id": "r1",
        },
    )
    snap = ctx.invocation_log.snapshot()
    assert len(snap) == 1
    assert snap[0]["status"] == "ok"
    assert snap[0]["capability"] == "arm.pick"
    assert snap[0]["manifest_path"] == str(ctx.manifest_path)


def test_result_without_call_is_ignored(tmp_path: Path):
    ctx = _fresh_ctx(tmp_path)
    ctx.publisher.publish(
        "tool.result",
        {"tool": "execute_capability", "status": "ok", "request_id": "orphan"},
    )
    assert ctx.invocation_log.snapshot() == []


def test_other_kinds_never_append(tmp_path: Path):
    ctx = _fresh_ctx(tmp_path)
    ctx.publisher.publish("estop.set", {"set": True})
    ctx.publisher.publish("frame", {"png_b64": "x"})
    assert ctx.invocation_log.snapshot() == []


def test_precondition_failure_carries_structured_preconditions(tmp_path: Path):
    ctx = _fresh_ctx(tmp_path)
    ctx.publisher.publish(
        "tool.call",
        {"tool": "execute_capability", "capability": "arm.pick", "args": {}, "request_id": "r2"},
    )
    ctx.publisher.publish(
        "tool.result",
        {
            "tool": "execute_capability",
            "capability": "arm.pick",
            "status": "blocked",
            "request_id": "r2",
            "error": {
                "reason": "precondition",
                "preconditions": [
                    {
                        "kind": "extrinsic_present",
                        "name": None,
                        "message": "hand-eye extrinsic missing",
                        "suggested_fix": "robot-md calibrate --hand-eye",
                    }
                ],
            },
        },
    )
    snap = ctx.invocation_log.snapshot()
    assert snap[0]["reason"] == "precondition"
    assert snap[0]["preconditions"][0]["suggested_fix"] == "robot-md calibrate --hand-eye"
