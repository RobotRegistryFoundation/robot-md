"""Unit tests for recent_invocations + recent_errors resource builders."""
from __future__ import annotations

from types import SimpleNamespace

from robot_md.mcp.invocation_log import InvocationLog
from robot_md.mcp.invocation_record import InvocationRecord
from robot_md.mcp.resources import recent_errors, recent_invocations


def _ctx_with_log(records: list[InvocationRecord]) -> SimpleNamespace:
    log = InvocationLog(maxlen=100)
    for r in records:
        log.append(r)
    return SimpleNamespace(invocation_log=log)


def _rec(i: int, status: str = "ok", reason: str | None = None) -> InvocationRecord:
    return InvocationRecord(
        timestamp=float(i),
        tool="execute_capability",
        capability="arm.pick",
        args={"i": i},
        status=status,
        reason=reason,
        request_id=f"r{i}",
        manifest_path="/M.md",
    )


def test_recent_invocations_returns_snapshot_newest_first():
    ctx = _ctx_with_log([_rec(1), _rec(2), _rec(3)])
    out = recent_invocations(ctx)
    assert [r["request_id"] for r in out] == ["r3", "r2", "r1"]


def test_recent_errors_filters_to_nonok():
    ctx = _ctx_with_log(
        [_rec(1, "ok"), _rec(2, "error", "ik_failed"), _rec(3, "blocked", "estop_set")]
    )
    out = recent_errors(ctx)
    assert [r["request_id"] for r in out] == ["r3", "r2"]
    assert all(r["status"] != "ok" for r in out)


def test_resources_with_missing_log_return_empty():
    ctx = SimpleNamespace()  # no invocation_log attr
    assert recent_invocations(ctx) == []
    assert recent_errors(ctx) == []


def test_resources_return_jsonable_dicts():
    import json

    ctx = _ctx_with_log([_rec(1)])
    json.dumps(recent_invocations(ctx))
    json.dumps(recent_errors(ctx))
