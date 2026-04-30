"""Hash-chained append-only event queue at ~/.robot-md/hotplug-events.jsonl.

Same shape as RRF's compliance audit trail: each record carries a sha256
of (prev_hash || canonical_json(record_minus_hash)), so any tampering is
detectable end-to-end.
"""

from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision


_DEFAULT_PATH = Path.home() / ".robot-md" / "hotplug-events.jsonl"
_ZERO_HASH = "sha256:" + "0" * 64


@dataclass(frozen=True)
class QueueRecord:
    id: str
    ts: str
    kind: str   # "pending" | "resolved" | "daemon_alert"
    event: dict | None
    decision: dict | None
    ref: str | None
    resolution: str | None
    by: str | None
    outcome: dict | None
    prev_hash: str
    this_hash: str


class AlreadyResolvedError(Exception):
    def __init__(self, *, ref_id: str, by: str) -> None:
        super().__init__(f"event {ref_id} already resolved by {by}")
        self.ref_id = ref_id
        self.by = by


def _hash_record(prev_hash: str, body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256()
    h.update(prev_hash.encode("ascii"))
    h.update(b"\0")
    h.update(canonical.encode("utf-8"))
    return "sha256:" + h.hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _decision_to_dict(d: Decision) -> dict:
    return dataclasses.asdict(d)


def _safe_iter_records(path: Path) -> tuple[list[dict], int]:
    """Return (parsed_records, count_of_dropped_malformed_lines)."""
    records: list[dict] = []
    dropped = 0
    if not path.exists():
        return records, 0
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            dropped += 1
    return records, dropped


class EventQueue:
    def __init__(self, *, path: Path = _DEFAULT_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._emit_alert_if_truncation_observed()

    def _last_hash(self) -> str:
        with self.path.open("rb") as f:
            data = f.read()
        if not data:
            return _ZERO_HASH
        last_line = data.rstrip(b"\n").rsplit(b"\n", 1)[-1]
        try:
            return json.loads(last_line)["this_hash"]
        except Exception:
            return _ZERO_HASH

    def _emit_alert_if_truncation_observed(self) -> None:
        _, dropped = _safe_iter_records(self.path)
        if dropped == 0:
            return
        # Make sure the alert lands on its own line even if the trailing
        # corrupt fragment lacks a newline terminator.
        with self.path.open("ab") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                tail = self.path.read_bytes()
                prefix = b"" if tail.endswith(b"\n") or not tail else b"\n"
                prev = self._last_hash()
                body = {
                    "id": "evt_" + uuid.uuid4().hex,
                    "ts": _now_iso(),
                    "kind": "daemon_alert",
                    "event": None,
                    "decision": None,
                    "ref": None,
                    "resolution": None,
                    "by": "daemon",
                    "outcome": {"msg": "queue tail truncated", "dropped": dropped},
                    "prev_hash": prev,
                }
                body["this_hash"] = _hash_record(prev, body)
                f.write(prefix + (json.dumps(body, sort_keys=True) + "\n").encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def append_pending(self, evt: DeviceEvent, decision: Decision) -> QueueRecord:
        with self.path.open("ab") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                prev = self._last_hash()
                body = {
                    "id": "evt_" + uuid.uuid4().hex,
                    "ts": _now_iso(),
                    "kind": "pending",
                    "event": asdict(evt),
                    "decision": _decision_to_dict(decision),
                    "ref": None,
                    "resolution": None,
                    "by": None,
                    "outcome": None,
                    "prev_hash": prev,
                }
                body["this_hash"] = _hash_record(prev, body)
                line = json.dumps(body, sort_keys=True) + "\n"
                f.write(line.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return QueueRecord(**body)

    def append_resolution(
        self,
        *,
        ref_id: str,
        resolution: str,
        by: str,
        outcome: dict | None,
    ) -> QueueRecord:
        # First-writer-wins: refuse a second resolution for the same pending id.
        records, _ = _safe_iter_records(self.path)
        for rec in records:
            if rec.get("kind") == "resolved" and rec.get("ref") == ref_id:
                raise AlreadyResolvedError(ref_id=ref_id, by=rec.get("by") or "unknown")
        with self.path.open("ab") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                prev = self._last_hash()
                body = {
                    "id": "evt_" + uuid.uuid4().hex,
                    "ts": _now_iso(),
                    "kind": "resolved",
                    "event": None,
                    "decision": None,
                    "ref": ref_id,
                    "resolution": resolution,
                    "by": by,
                    "outcome": outcome,
                    "prev_hash": prev,
                }
                body["this_hash"] = _hash_record(prev, body)
                line = json.dumps(body, sort_keys=True) + "\n"
                f.write(line.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return QueueRecord(**body)

    def expire_old(self, *, ttl_days: float) -> list[str]:
        """Append a 'resolution=expired' for every still-pending event whose
        underlying DeviceEvent.detected_at is older than ttl_days. Returns
        the list of pending ids that were expired in this call.
        """
        records, _ = _safe_iter_records(self.path)
        now = datetime.now(timezone.utc)
        threshold = timedelta(days=ttl_days)

        pending_by_id = {r["id"]: r for r in records if r.get("kind") == "pending"}
        resolved_refs = {r["ref"] for r in records if r.get("kind") == "resolved" and r.get("ref")}

        expired_ids: list[str] = []
        for rid, rec in pending_by_id.items():
            if rid in resolved_refs:
                continue
            evt = rec.get("event") or {}
            detected_at = evt.get("detected_at") or rec.get("ts")
            if not detected_at:
                continue
            try:
                ts = datetime.fromisoformat(detected_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if (now - ts) > threshold:
                self.append_resolution(ref_id=rid, resolution="expired", by="daemon", outcome=None)
                expired_ids.append(rid)
        return expired_ids
