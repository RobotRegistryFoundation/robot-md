"""Unit tests for InvocationLog ring buffer."""

from __future__ import annotations

import threading

from robot_md.mcp.invocation_log import InvocationLog
from robot_md.mcp.invocation_record import InvocationRecord


def _rec(i: int, status: str = "ok", reason: str | None = None) -> InvocationRecord:
    return InvocationRecord(
        timestamp=float(i),
        tool="execute_capability",
        capability="arm.pick",
        args={"i": i},
        status=status,
        reason=reason,
        request_id=f"r{i}",
        manifest_path="/tmp/M.md",
    )


def test_append_and_snapshot_newest_first():
    log = InvocationLog(maxlen=10)
    for i in range(3):
        log.append(_rec(i))
    snap = log.snapshot()
    assert [s["request_id"] for s in snap] == ["r2", "r1", "r0"]


def test_snapshot_returns_jsonable_dicts():
    log = InvocationLog(maxlen=10)
    log.append(_rec(1))
    import json

    snap = log.snapshot()
    json.dumps(snap)  # must not raise


def test_ring_bounds_evict_oldest():
    log = InvocationLog(maxlen=3)
    for i in range(5):
        log.append(_rec(i))
    snap = log.snapshot()
    assert [s["request_id"] for s in snap] == ["r4", "r3", "r2"]
    assert len(snap) == 3


def test_snapshot_errors_filters_by_status():
    log = InvocationLog(maxlen=10)
    log.append(_rec(1, status="ok"))
    log.append(_rec(2, status="error", reason="ik_failed"))
    log.append(_rec(3, status="blocked", reason="estop_set"))
    log.append(_rec(4, status="ok"))
    errors = log.snapshot_errors()
    assert [e["request_id"] for e in errors] == ["r3", "r2"]


def test_snapshot_empty():
    log = InvocationLog(maxlen=10)
    assert log.snapshot() == []
    assert log.snapshot_errors() == []


def test_concurrent_append_and_snapshot_thread_safe():
    log = InvocationLog(maxlen=200)

    def writer():
        for i in range(500):
            log.append(_rec(i))

    def reader():
        for _ in range(500):
            snap = log.snapshot()
            for s in snap:
                assert "request_id" in s

    threads = [threading.Thread(target=writer) for _ in range(2)] + [
        threading.Thread(target=reader) for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
        assert not t.is_alive()
