"""Unit tests for InvocationLog.backfill_from_jsonl()."""

from __future__ import annotations

import json
from pathlib import Path

from robot_md.mcp.invocation_log import InvocationLog


def _write_jsonl(path: Path, events: list[dict]) -> None:
    with path.open("w") as f:
        for evt in events:
            f.write(json.dumps(evt) + "\n")


def _call(request_id: str, manifest: str, ts: float = 1.0) -> dict:
    return {
        "kind": "tool.call",
        "ts": ts,
        "data": {
            "tool": "execute_capability",
            "capability": "arm.pick",
            "args": {},
            "request_id": request_id,
            "manifest_path": manifest,
        },
    }


def _result(request_id: str, manifest: str, status: str = "ok", ts: float = 2.0) -> dict:
    return {
        "kind": "tool.result",
        "ts": ts,
        "data": {
            "tool": "execute_capability",
            "capability": "arm.pick",
            "status": status,
            "request_id": request_id,
            "manifest_path": manifest,
        },
    }


def test_backfill_pairs_call_and_result(tmp_path: Path):
    p = tmp_path / "events.jsonl"
    _write_jsonl(p, [_call("r1", "/M.md"), _result("r1", "/M.md")])
    log = InvocationLog(maxlen=100)
    log.backfill_from_jsonl(p, manifest_path="/M.md", n=100)
    snap = log.snapshot()
    assert len(snap) == 1
    assert snap[0]["request_id"] == "r1"
    assert snap[0]["status"] == "ok"


def test_backfill_filters_by_manifest_path(tmp_path: Path):
    p = tmp_path / "events.jsonl"
    _write_jsonl(
        p,
        [
            _call("r1", "/A.md"),
            _result("r1", "/A.md"),
            _call("r2", "/B.md"),
            _result("r2", "/B.md"),
        ],
    )
    log = InvocationLog(maxlen=100)
    log.backfill_from_jsonl(p, manifest_path="/A.md", n=100)
    snap = log.snapshot()
    assert [s["request_id"] for s in snap] == ["r1"]


def test_backfill_drops_unpaired_call(tmp_path: Path):
    p = tmp_path / "events.jsonl"
    _write_jsonl(p, [_call("r_orphan", "/M.md"), _call("r1", "/M.md"), _result("r1", "/M.md")])
    log = InvocationLog(maxlen=100)
    log.backfill_from_jsonl(p, manifest_path="/M.md", n=100)
    snap = log.snapshot()
    assert [s["request_id"] for s in snap] == ["r1"]


def test_backfill_honors_n_limit(tmp_path: Path):
    p = tmp_path / "events.jsonl"
    pairs = []
    for i in range(10):
        pairs.extend(
            [_call(f"r{i}", "/M.md", ts=float(i)), _result(f"r{i}", "/M.md", ts=float(i) + 0.5)]
        )
    _write_jsonl(p, pairs)
    log = InvocationLog(maxlen=100)
    log.backfill_from_jsonl(p, manifest_path="/M.md", n=3)
    snap = log.snapshot()
    # Most recent 3 pairs → r7/r8/r9, newest-first.
    assert [s["request_id"] for s in snap] == ["r9", "r8", "r7"]


def test_backfill_missing_file_is_noop(tmp_path: Path):
    log = InvocationLog(maxlen=100)
    log.backfill_from_jsonl(tmp_path / "nope.jsonl", manifest_path="/M.md", n=100)
    assert log.snapshot() == []


def test_backfill_malformed_line_skipped(tmp_path: Path):
    p = tmp_path / "events.jsonl"
    with p.open("w") as f:
        f.write("this is not json\n")
        f.write(json.dumps(_call("r1", "/M.md")) + "\n")
        f.write("{broken\n")
        f.write(json.dumps(_result("r1", "/M.md")) + "\n")
    log = InvocationLog(maxlen=100)
    log.backfill_from_jsonl(p, manifest_path="/M.md", n=100)
    snap = log.snapshot()
    assert [s["request_id"] for s in snap] == ["r1"]


def test_backfill_ignores_non_tool_events(tmp_path: Path):
    p = tmp_path / "events.jsonl"
    _write_jsonl(
        p,
        [
            {"kind": "estop.set", "ts": 1.0, "data": {"set": True, "manifest_path": "/M.md"}},
            _call("r1", "/M.md"),
            _result("r1", "/M.md"),
            {"kind": "frame", "ts": 3.0, "data": {"manifest_path": "/M.md"}},
        ],
    )
    log = InvocationLog(maxlen=100)
    log.backfill_from_jsonl(p, manifest_path="/M.md", n=100)
    snap = log.snapshot()
    assert [s["request_id"] for s in snap] == ["r1"]
