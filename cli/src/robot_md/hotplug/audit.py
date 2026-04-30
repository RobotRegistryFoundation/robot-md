"""Per-RRN hash-chained audit log. Mirrors RRF's audit trail shape."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_ROOT = Path.home() / ".robot-md" / "audit"
_ZERO_HASH = "sha256:" + "0" * 64


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash(prev: str, body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256()
    h.update(prev.encode("ascii"))
    h.update(b"\0")
    h.update(canonical.encode("utf-8"))
    return "sha256:" + h.hexdigest()


class AuditLog:
    def __init__(self, *, rrn: str, root: Path = _DEFAULT_ROOT) -> None:
        self.rrn = rrn
        self.path = root / f"{rrn}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _last_hash(self) -> str:
        data = self.path.read_bytes().rstrip(b"\n")
        if not data:
            return _ZERO_HASH
        try:
            return json.loads(data.rsplit(b"\n", 1)[-1])["this_hash"]
        except Exception:
            return _ZERO_HASH

    def append(self, kind: str, payload: dict) -> dict:
        with self.path.open("ab") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                prev = self._last_hash()
                body = {
                    "id": "audit_" + uuid.uuid4().hex,
                    "ts": _now_iso(),
                    "rrn": self.rrn,
                    "kind": kind,
                    "payload": payload,
                    "prev_hash": prev,
                }
                body["this_hash"] = _hash(prev, body)
                f.write((json.dumps(body, sort_keys=True) + "\n").encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return body
