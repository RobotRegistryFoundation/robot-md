"""Unit tests for InvocationRecord + from_event_pair()."""

from __future__ import annotations

import pytest

from robot_md.mcp.invocation_record import InvocationRecord


def _call_evt(request_id="r1", capability="arm.pick", args=None):
    return {
        "kind": "tool.call",
        "ts": 100.0,
        "data": {
            "tool": "execute_capability",
            "capability": capability,
            "args": args or {"object": "lego"},
            "dry_run": False,
            "request_id": request_id,
            "manifest_path": "/tmp/ROBOT.md",
        },
    }


def _result_evt(request_id="r1", status="ok", error=None):
    return {
        "kind": "tool.result",
        "ts": 101.5,
        "data": {
            "tool": "execute_capability",
            "capability": "arm.pick",
            "status": status,
            "request_id": request_id,
            "manifest_path": "/tmp/ROBOT.md",
            **({"error": error} if error is not None else {}),
        },
    }


def test_from_event_pair_success():
    rec = InvocationRecord.from_event_pair(_call_evt(), _result_evt())
    assert rec.tool == "execute_capability"
    assert rec.capability == "arm.pick"
    assert rec.args == {"object": "lego"}
    assert rec.status == "ok"
    assert rec.reason is None
    assert rec.preconditions == []
    assert rec.request_id == "r1"
    assert rec.manifest_path == "/tmp/ROBOT.md"
    assert rec.timestamp == 101.5  # result timestamp


def test_from_event_pair_precondition_failure():
    err = {
        "reason": "precondition",
        "preconditions": [
            {
                "kind": "extrinsic_present",
                "name": None,
                "message": "hand-eye extrinsic missing",
                "suggested_fix": "robot-md calibrate --hand-eye",
            }
        ],
    }
    rec = InvocationRecord.from_event_pair(_call_evt(), _result_evt(status="blocked", error=err))
    assert rec.status == "blocked"
    assert rec.reason == "precondition"
    assert len(rec.preconditions) == 1
    assert rec.preconditions[0]["suggested_fix"] == "robot-md calibrate --hand-eye"


def test_from_event_pair_estop():
    rec = InvocationRecord.from_event_pair(
        _call_evt(),
        _result_evt(status="blocked", error={"reason": "estop_set"}),
    )
    assert rec.status == "blocked"
    assert rec.reason == "estop_set"
    assert rec.preconditions == []


def test_from_event_pair_raw_exec_error():
    rec = InvocationRecord.from_event_pair(
        _call_evt(),
        _result_evt(status="error", error={"reason": "ik_failed"}),
    )
    assert rec.status == "error"
    assert rec.reason == "ik_failed"


def test_from_event_pair_mismatched_request_id_raises():
    with pytest.raises(ValueError, match="request_id mismatch"):
        InvocationRecord.from_event_pair(_call_evt(request_id="r1"), _result_evt(request_id="r2"))


def test_from_event_pair_non_execute_capability_has_null_capability():
    call = {
        "kind": "tool.call",
        "ts": 10.0,
        "data": {
            "tool": "discover",
            "args": {"steps": []},
            "request_id": "r9",
            "manifest_path": "/tmp/ROBOT.md",
        },
    }
    result = {
        "kind": "tool.result",
        "ts": 11.0,
        "data": {
            "tool": "discover",
            "status": "ok",
            "request_id": "r9",
            "manifest_path": "/tmp/ROBOT.md",
        },
    }
    rec = InvocationRecord.from_event_pair(call, result)
    assert rec.tool == "discover"
    assert rec.capability is None
    assert rec.status == "ok"
