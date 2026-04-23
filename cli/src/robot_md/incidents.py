"""§25 Post-Market Monitoring — append-only incident log + Art. 72 report.

Per-robot JSONL at ~/.robot-md/incidents/<rrn>.jsonl. Each line is a
complete rcan-incidents-v1 entry. Append-only — open-append-close per
record; load reads the whole file. Size stays manageable in practice
(serious incidents are rare); if it grows unbounded, operators rotate
manually.

Entry shape (rcan-spec §25):
- id           UUID v4 (deduplication)
- timestamp    ISO-8601 UTC
- severity     "life_health" (15-day deadline) | "other" (90-day)
- category     short category tag, e.g. "motor_stall"
- description  human-readable description
- system_state snapshot dict (optional by spec, always written as {})

Report shape (rcan-incidents-v1):
- schema, generated_at, rrn, total_incidents,
  incidents_by_severity{life_health, other},
  reporting_deadlines, art72_note, incidents[]
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

INCIDENTS_SCHEMA_NAME = "rcan-incidents-v1"
VALID_SEVERITIES: tuple[Literal["life_health"], Literal["other"]] = (
    "life_health",
    "other",
)
REPORTING_DEADLINES = {
    "life_health": "15 days from incident timestamp",
    "other": "90 days from incident timestamp",
}
ART72_NOTE = (
    "Providers must report serious incidents to the relevant national "
    "authority within the applicable deadline per EU AI Act Art. 72."
)


def _log_dir() -> Path:
    """Dynamic so HOME monkeypatching in tests works."""
    return Path.home() / ".robot-md" / "incidents"


def _log_path(rrn: str) -> Path:
    return _log_dir() / f"{rrn}.jsonl"


def record(
    rrn: str,
    *,
    severity: str,
    category: str,
    description: str,
    system_state: dict | None = None,
) -> dict:
    """Append a new incident entry for `rrn`. Returns the entry as written."""
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"severity must be one of {VALID_SEVERITIES}, got {severity!r}")
    if not category.strip():
        raise ValueError("category required")
    if not description.strip():
        raise ValueError("description required")

    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "severity": severity,
        "category": category,
        "description": description,
        "system_state": system_state or {},
    }
    path = _log_path(rrn)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def load(rrn: str) -> list[dict]:
    """Return all incidents for `rrn`, newest first. Empty list if none."""
    path = _log_path(rrn)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    entries = [json.loads(ln) for ln in lines if ln.strip()]
    return sorted(entries, key=lambda e: e.get("timestamp", ""), reverse=True)


def build_report(rrn: str) -> dict:
    """Emit an rcan-incidents-v1 report summarizing all logged incidents."""
    entries = load(rrn)
    by_severity = dict.fromkeys(VALID_SEVERITIES, 0)
    for e in entries:
        sev = e.get("severity")
        if sev in by_severity:
            by_severity[sev] += 1
    return {
        "schema": INCIDENTS_SCHEMA_NAME,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "rrn": rrn,
        "total_incidents": len(entries),
        "incidents_by_severity": by_severity,
        "reporting_deadlines": dict(REPORTING_DEADLINES),
        "art72_note": ART72_NOTE,
        "incidents": entries,
    }


def sign_artifact(artifact: dict, rrn: str) -> dict:
    """Route a report through v0.9.1 signing.sign_body (same wire format as
    register, §23 benchmarks, §24 IFU). Returns a new dict. Raises
    RuntimeError if the keystore has no signing key for `rrn`.
    """
    from robot_md.signing import load_keypair, sign_body

    kp = load_keypair(rrn)
    if kp is None:
        raise RuntimeError(
            f"no signing keypair for {rrn} at ~/.robot-md/keys/. "
            f"Run `robot-md register <manifest>` to mint one."
        )
    return sign_body(kp, artifact)
