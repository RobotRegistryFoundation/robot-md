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
from datetime import datetime, timezone
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


class EventQueue:
    def __init__(self, *, path: Path = _DEFAULT_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

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
