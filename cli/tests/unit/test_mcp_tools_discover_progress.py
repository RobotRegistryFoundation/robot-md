"""Unit tests for discover_tool streaming — report_progress + discover.step.* events."""

from __future__ import annotations

from types import SimpleNamespace

from robot_md.mcp.tools.discover import discover_tool


class _StubMcpContext:
    def __init__(self):
        self.progress_calls: list[tuple[int, int, str]] = []

    async def report_progress(self, progress, total, message=None):
        self.progress_calls.append((progress, total, message))


class _FakePublisher:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def publish(self, kind, data):
        self.events.append((kind, dict(data)))


def _ctx_no_backend():
    return SimpleNamespace(backend=None, publisher=_FakePublisher())


async def test_discover_calls_report_progress_once_per_step():
    ctx = _ctx_no_backend()
    mcp = _StubMcpContext()
    steps = [{"capture": {}}, {"detect": {"descriptors": []}}]
    await discover_tool(ctx, steps=steps, mcp_ctx=mcp)
    assert len(mcp.progress_calls) == 2
    assert mcp.progress_calls[0][0] == 0
    assert mcp.progress_calls[0][1] == 2
    assert mcp.progress_calls[0][2] == "capture"
    assert mcp.progress_calls[1][2] == "detect"


async def test_discover_publishes_step_begin_and_end_events():
    ctx = _ctx_no_backend()
    steps = [{"capture": {}}]
    await discover_tool(ctx, steps=steps, mcp_ctx=None)
    kinds = [e[0] for e in ctx.publisher.events]
    assert kinds == ["discover.step.begin", "discover.step.end"]
    begin_data = ctx.publisher.events[0][1]
    assert begin_data["name"] == "capture"
    assert begin_data["i"] == 0
    assert begin_data["total"] == 1
    end_data = ctx.publisher.events[1][1]
    assert end_data["name"] == "capture"
    assert "status" in end_data


async def test_discover_works_when_mcp_ctx_is_none():
    """No FastMCP Context (direct call, tests) → report_progress skipped,
    JSONL events still fire."""
    ctx = _ctx_no_backend()
    out = await discover_tool(ctx, steps=[{"capture": {}}], mcp_ctx=None)
    assert out["status"] == "ok"
    assert any(e[0] == "discover.step.begin" for e in ctx.publisher.events)


async def test_discover_swallows_report_progress_exceptions():
    ctx = _ctx_no_backend()

    class _Broken:
        async def report_progress(self, *a, **kw):
            raise RuntimeError("boom")

    out = await discover_tool(ctx, steps=[{"capture": {}}], mcp_ctx=_Broken())
    assert out["status"] == "ok"


async def test_discover_no_publisher_does_not_crash():
    """Observability is best-effort — ctx without a publisher still works."""
    ctx = SimpleNamespace(backend=None, publisher=None)
    out = await discover_tool(ctx, steps=[{"capture": {}}], mcp_ctx=None)
    assert out["status"] == "ok"


async def test_discover_malformed_step_still_counted_for_progress():
    """A step with >1 key is skipped by the dispatcher but still counts
    toward total/report_progress — otherwise progress drifts."""
    ctx = _ctx_no_backend()
    mcp = _StubMcpContext()
    # A malformed step (not a dict-with-single-key) is silently skipped per
    # the existing v0.7 contract; streaming must not crash on it.
    steps = [{"capture": {}}, "not a dict", {"detect": {"descriptors": []}}]
    await discover_tool(ctx, steps=steps, mcp_ctx=mcp)
    # Two valid steps → two progress calls (indices 0 and 2).
    assert [(p[0], p[2]) for p in mcp.progress_calls] == [(0, "capture"), (2, "detect")]
