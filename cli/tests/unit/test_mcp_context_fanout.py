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


def test_install_fanout_is_idempotent(tmp_path: Path):
    """Calling _install_publisher_fanout twice must not double-wrap."""
    from robot_md.mcp.context import _PublisherFanoutWrapper

    ctx = _fresh_ctx(tmp_path)
    # _fresh_ctx already installed the fanout once — wrapper is in place.
    assert isinstance(ctx.publisher, _PublisherFanoutWrapper)
    inner_before = ctx.publisher._inner

    _install_publisher_fanout(ctx)  # second install
    assert isinstance(ctx.publisher, _PublisherFanoutWrapper)
    # Same inner — no wrapper-of-wrapper.
    assert ctx.publisher._inner is inner_before


def test_install_fanout_with_none_publisher_is_noop(tmp_path: Path):
    """When ctx.publisher is None (dashboard disabled), install is a no-op."""
    manifest = tmp_path / "M.md"
    manifest.write_text("")
    ctx = McpContext(manifest_path=manifest, parsed=None)
    ctx.publisher = None

    _install_publisher_fanout(ctx)
    assert ctx.publisher is None  # still None, no wrapper constructed


def test_pending_calls_expire_after_ttl(tmp_path: Path, monkeypatch):
    """A tool.call with no matching result older than _PENDING_TTL_S is
    swept on the next call."""
    from robot_md.mcp import context as ctx_mod

    ctx = _fresh_ctx(tmp_path)
    # Freeze time at t0 for the orphan call.
    times = [1000.0]
    monkeypatch.setattr(ctx_mod.time, "time", lambda: times[0])

    ctx.publisher.publish(
        "tool.call",
        {"tool": "execute_capability", "capability": "arm.pick", "args": {}, "request_id": "orphan"},
    )
    assert "orphan" in ctx._pending_calls  # parked

    # Jump forward past the TTL.
    times[0] = 1000.0 + ctx_mod._PENDING_TTL_S + 1.0

    # A new call at t1 triggers the sweep inside _maybe_pair_and_log.
    ctx.publisher.publish(
        "tool.call",
        {"tool": "execute_capability", "capability": "arm.place", "args": {}, "request_id": "fresh"},
    )
    assert "orphan" not in ctx._pending_calls
    assert "fresh" in ctx._pending_calls


def test_load_context_wires_fanout_and_backfills(tmp_path: Path, monkeypatch):
    """load_context must install the fanout wrapper AND backfill the log
    from ~/.robot-md/events.jsonl for this manifest."""
    import json as _json

    # Steer the publisher to a temp HOME so events.jsonl is isolated.
    monkeypatch.setenv("HOME", str(tmp_path))
    # Disable the WS port to avoid port binding during unit tests.
    monkeypatch.setenv("ROBOT_MD_DASHBOARD_DISABLED", "0")

    events_dir = tmp_path / ".robot-md"
    events_dir.mkdir()
    events_path = events_dir / "events.jsonl"

    # Build a fixture manifest path that matches what we'll stamp in the JSONL.
    # We use a valid fixture manifest from the repo.
    from pathlib import Path as _P

    fix = _P(__file__).parent.parent / "fixtures" / "robot_md_oak_d_factory_cal.yaml"
    manifest_path_str = str(fix)

    # Pre-seed events.jsonl with a paired invocation for this manifest.
    call = {
        "kind": "tool.call", "ts": 1.0,
        "data": {
            "tool": "execute_capability", "capability": "arm.pick",
            "args": {}, "request_id": "pre_r1", "manifest_path": manifest_path_str,
        },
    }
    result = {
        "kind": "tool.result", "ts": 2.0,
        "data": {
            "tool": "execute_capability", "capability": "arm.pick",
            "status": "ok", "request_id": "pre_r1", "manifest_path": manifest_path_str,
        },
    }
    with events_path.open("w") as f:
        f.write(_json.dumps(call) + "\n")
        f.write(_json.dumps(result) + "\n")

    from robot_md.mcp.context import load_context, _PublisherFanoutWrapper

    ctx = load_context(fix)
    try:
        # Fanout installed.
        assert isinstance(ctx.publisher, _PublisherFanoutWrapper)

        # Backfill replayed the pre-seeded pair.
        snap = ctx.invocation_log.snapshot()
        assert any(s["request_id"] == "pre_r1" for s in snap)
    finally:
        if ctx.publisher is not None:
            inner = getattr(ctx.publisher, "_inner", None)
            if inner is not None and hasattr(inner, "stop"):
                inner.stop()
