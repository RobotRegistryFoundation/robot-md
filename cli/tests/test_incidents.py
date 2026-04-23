"""v0.9.4 — §25 PMM incident log tests."""

from __future__ import annotations

import json

import pytest

from robot_md.incidents import (
    ART72_NOTE,
    INCIDENTS_SCHEMA_NAME,
    REPORTING_DEADLINES,
    VALID_SEVERITIES,
    _log_path,
    build_report,
    load,
    record,
    sign_artifact,
)

# ---- record -------------------------------------------------------


def test_record_appends_entry_to_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    entry = record(
        "RRN-000000000042",
        severity="life_health",
        category="motor_stall",
        description="Left drive stalled under load",
        system_state={"duty": 0.85},
    )
    path = tmp_path / ".robot-md" / "incidents" / "RRN-000000000042.jsonl"
    assert path.exists()
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert stored == entry
    assert stored["severity"] == "life_health"
    assert stored["category"] == "motor_stall"
    assert stored["system_state"] == {"duty": 0.85}
    # UUID v4 is 36 chars including hyphens
    assert len(stored["id"]) == 36


def test_record_returns_entry_with_uuid_and_timestamp(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    entry = record(
        "RRN-000000000042",
        severity="other",
        category="provider_timeout",
        description="AI provider response timed out",
    )
    assert entry["severity"] == "other"
    assert entry["timestamp"].endswith("Z")
    assert entry["system_state"] == {}  # default


def test_record_rejects_invalid_severity(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ValueError, match="severity"):
        record(
            "RRN-000000000042",
            severity="catastrophic",
            category="motor_stall",
            description="…",
        )


def test_record_rejects_empty_category_and_description(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ValueError, match="category"):
        record(
            "RRN-000000000042",
            severity="other",
            category="",
            description="detail",
        )
    with pytest.raises(ValueError, match="description"):
        record(
            "RRN-000000000042",
            severity="other",
            category="motor_stall",
            description="",
        )


def test_record_is_append_only_two_entries_same_robot(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    record(
        "RRN-000000000042",
        severity="other",
        category="a",
        description="first",
    )
    record(
        "RRN-000000000042",
        severity="other",
        category="b",
        description="second",
    )
    path = _log_path("RRN-000000000042")
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2


# ---- load ---------------------------------------------------------


def test_load_returns_empty_when_no_log(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert load("RRN-000000000042") == []


def test_load_sorts_newest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / ".robot-md" / "incidents" / "RRN-000000000042.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(
            [
                json.dumps({"id": "1", "timestamp": "2026-01-01T00:00:00Z", "severity": "other"}),
                json.dumps({"id": "2", "timestamp": "2026-03-01T00:00:00Z", "severity": "other"}),
                json.dumps({"id": "3", "timestamp": "2026-02-01T00:00:00Z", "severity": "other"}),
            ]
        )
    )
    ids = [e["id"] for e in load("RRN-000000000042")]
    assert ids == ["2", "3", "1"]


# ---- build_report ------------------------------------------------


def test_build_report_empty_log_returns_zeroed_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    r = build_report("RRN-000000000042")
    assert r["schema"] == INCIDENTS_SCHEMA_NAME
    assert r["rrn"] == "RRN-000000000042"
    assert r["total_incidents"] == 0
    assert r["incidents_by_severity"] == {s: 0 for s in VALID_SEVERITIES}
    assert r["reporting_deadlines"] == REPORTING_DEADLINES
    assert r["art72_note"] == ART72_NOTE
    assert r["incidents"] == []


def test_build_report_counts_by_severity(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    for _ in range(2):
        record(
            "RRN-000000000042",
            severity="life_health",
            category="motor_stall",
            description="d",
        )
    record(
        "RRN-000000000042",
        severity="other",
        category="timeout",
        description="d",
    )
    r = build_report("RRN-000000000042")
    assert r["total_incidents"] == 3
    assert r["incidents_by_severity"]["life_health"] == 2
    assert r["incidents_by_severity"]["other"] == 1
    assert len(r["incidents"]) == 3


# ---- sign -------------------------------------------------------


def test_report_sign_and_verify_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from robot_md.signing import generate_keypair, save_keypair, verify_body

    save_keypair("RRN-000000000042", generate_keypair())
    record(
        "RRN-000000000042",
        severity="other",
        category="test",
        description="d",
    )
    r = build_report("RRN-000000000042")
    signed = sign_artifact(r, rrn="RRN-000000000042")
    _ = json.dumps(signed, sort_keys=True)
    assert verify_body(signed) is True
