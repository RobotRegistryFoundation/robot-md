"""Hash-chained append-only audit log for robot-md (P2.2).

Per-robot log at ~/.robot-md/audit/<rrn>.jsonl. Each entry includes
``prev_hash`` (the entry_hash of the previous entry, or GENESIS_PREV_HASH
for the first entry) and ``entry_hash`` (sha256 of the canonical
JSON-serialized entry without the entry_hash itself). Any historical edit
breaks the chain.

Used by submit.py to record RRF submissions, by P3 (MCP safety gate) to
record gate firings, and by `robot-md audit verify` to walk the chain.

Limitations:
- Truncation of trailing entries is undetectable from the log alone — a
  notified body needs an external witness (e.g., a periodic checkpoint
  countersigned by RRF) to detect "the log used to be longer." Documented
  here so the limitation is explicit, not surprising.
- Replacing the entire log with a self-consistent shorter history is
  detectable by RRF if RRF holds the latest known entry_hash for the rrn.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS_PREV_HASH = "0" * 64


class AuditChainError(RuntimeError):
    """Raised by verify_chain when the chain integrity is broken."""


def _log_dir() -> Path:
    return Path.home() / ".robot-md" / "audit"


def _log_path(rrn: str) -> Path:
    return _log_dir() / f"{rrn}.jsonl"


def _canonical_for_hash(entry_without_hash: dict) -> bytes:
    """Canonical-JSON serialization for hashing. Must be deterministic.

    Sorts keys, no whitespace, ensures no NaN/Infinity floats slip through.
    """
    return json.dumps(
        entry_without_hash,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _last_entry_hash(rrn: str) -> str:
    """Return the entry_hash of the last entry in the log, or GENESIS_PREV_HASH."""
    path = _log_path(rrn)
    if not path.exists():
        return GENESIS_PREV_HASH
    last_line = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            last_line = line
    if not last_line:
        return GENESIS_PREV_HASH
    return json.loads(last_line)["entry_hash"]


def record_event(
    rrn: str,
    *,
    event: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append an audit entry for `rrn`. Returns the entry as written.

    `event` is a short tag (e.g. "submission", "safety_gate_denied",
    "key_rotated"). `details` is an arbitrary JSON-serialisable dict.
    """
    prev_hash = _last_entry_hash(rrn)
    entry_no_hash: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "rrn": rrn,
        "event": event,
        "details": details or {},
        "prev_hash": prev_hash,
    }
    entry_hash = hashlib.sha256(_canonical_for_hash(entry_no_hash)).hexdigest()
    entry = {**entry_no_hash, "entry_hash": entry_hash}

    path = _log_path(rrn)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def load_entries(rrn: str) -> list[dict[str, Any]]:
    """Return all audit entries for `rrn` in append order, or empty."""
    path = _log_path(rrn)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def verify_chain(rrn: str) -> dict[str, Any]:
    """Walk the chain. Return {'valid': True, 'entries': N} on success.

    Raises AuditChainError on any of:
    - entry_hash doesn't match recomputed canonical hash (mid-stream tamper)
    - prev_hash doesn't match the previous entry's entry_hash (chain split)
    """
    entries = load_entries(rrn)
    expected_prev = GENESIS_PREV_HASH
    for i, entry in enumerate(entries):
        if entry["prev_hash"] != expected_prev:
            raise AuditChainError(
                f"entry {i} prev_hash mismatch: expected {expected_prev}, got {entry['prev_hash']}"
            )
        recomputed = hashlib.sha256(
            _canonical_for_hash({k: v for k, v in entry.items() if k != "entry_hash"})
        ).hexdigest()
        if recomputed != entry["entry_hash"]:
            raise AuditChainError(
                f"entry {i} entry_hash mismatch: stored={entry['entry_hash']}, "
                f"recomputed={recomputed}"
            )
        expected_prev = entry["entry_hash"]
    return {"valid": True, "entries": len(entries)}
