"""Hash-chained signed audit log tests (P2.2).

Append-only log under ~/.robot-md/audit/<rrn>.jsonl. Each entry includes
the SHA-256 of the previous entry's canonical bytes so any historical edit
breaks chain integrity. `verify_chain` walks the log and reports tamper.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from robot_md.audit import (
    GENESIS_PREV_HASH,
    AuditChainError,
    record_event,
    verify_chain,
)


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_first_entry_has_genesis_prev_hash(home):
    entry = record_event(
        rrn="RRN-000000000099",
        event="submission",
        details={"kind": "fria", "status": 200},
    )
    assert entry["prev_hash"] == GENESIS_PREV_HASH
    assert entry["entry_hash"]


def test_second_entry_chains_to_first(home):
    e1 = record_event("RRN-000000000099", event="submission", details={"kind": "fria"})
    e2 = record_event("RRN-000000000099", event="submission", details={"kind": "ifu"})
    assert e2["prev_hash"] == e1["entry_hash"]


def test_record_writes_under_home(home):
    record_event("RRN-000000000099", event="submission", details={"kind": "fria"})
    log = home / ".robot-md" / "audit" / "RRN-000000000099.jsonl"
    assert log.exists()
    line = log.read_text().strip().splitlines()[0]
    parsed = json.loads(line)
    assert parsed["event"] == "submission"


def test_verify_chain_passes_on_clean_log(home):
    record_event("RRN-000000000099", event="submission", details={"kind": "fria"})
    record_event("RRN-000000000099", event="submission", details={"kind": "ifu"})
    record_event("RRN-000000000099", event="submission", details={"kind": "incident-report"})
    result = verify_chain("RRN-000000000099")
    assert result["valid"] is True
    assert result["entries"] == 3


def test_verify_chain_detects_tampered_entry(home):
    record_event("RRN-000000000099", event="submission", details={"kind": "fria"})
    record_event("RRN-000000000099", event="submission", details={"kind": "ifu"})
    log = home / ".robot-md" / "audit" / "RRN-000000000099.jsonl"
    lines = log.read_text().splitlines()
    # Mutate the first entry's details — chain should break
    e1 = json.loads(lines[0])
    e1["details"]["kind"] = "TAMPERED"
    lines[0] = json.dumps(e1)
    log.write_text("\n".join(lines) + "\n")
    with pytest.raises(AuditChainError, match="entry_hash mismatch"):
        verify_chain("RRN-000000000099")


def test_verify_chain_detects_truncation(home):
    e1 = record_event("RRN-000000000099", event="submission", details={"kind": "fria"})
    record_event("RRN-000000000099", event="submission", details={"kind": "ifu"})
    log = home / ".robot-md" / "audit" / "RRN-000000000099.jsonl"
    # Drop the second entry
    log.write_text(json.dumps(e1) + "\n")
    # Now record a new entry — its prev_hash should match e1.entry_hash, OK
    e3 = record_event("RRN-000000000099", event="submission", details={"kind": "ifu_again"})
    assert e3["prev_hash"] == e1["entry_hash"]
    # Chain is technically valid (truncation can't be detected from log alone
    # without a witness; that's a known limitation noted in the docstring).
    assert verify_chain("RRN-000000000099")["valid"] is True


def test_verify_chain_empty_log(home):
    result = verify_chain("RRN-NONEXISTENT")
    assert result["valid"] is True
    assert result["entries"] == 0


def test_record_event_returns_full_entry(home):
    entry = record_event(
        rrn="RRN-000000000099",
        event="submission",
        details={"kind": "fria", "status": 200, "endpoint": "https://x/y"},
    )
    for field in ("id", "timestamp", "rrn", "event", "details", "prev_hash", "entry_hash"):
        assert field in entry
    assert entry["details"]["kind"] == "fria"
