"""`robot-md rotate-key` — rotate a robot's signing key at the Robot Registry Foundation.

Generates a new ML-DSA-65 + Ed25519 keypair locally, signs the rotation
canonical body with BOTH the old key and the new key, and POSTs both
signatures to RRF. On a 200 response the old keypair is archived and the
keystore is updated atomically.

Usage via CLI:

    robot-md rotate-key RRN-000000000042
    robot-md rotate-key RRN-000000000042 --endpoint https://staging.rrf...

Exit codes:
    0   — success (server accepted, local keystore updated)
    1   — failure (pre-flight check, server error, network error)
    2   — partial failure: server accepted BUT a local disk step failed
          (archive-write OR keystore-save). The server now expects the NEW
          key. The staged new keypair at ~/.robot-md/keys/<rrn>.NEW.signing.json
          holds recoverable material; stderr prints the exact `mv` command.

Critical ordering constraint
----------------------------
Before the POST: the freshly-generated new keypair is persisted to
``~/.robot-md/keys/<rrn>.NEW.signing.json`` (mode 0o600) so that any
exit-2 path has real key material to recover from.

After a 200 response: archive the old keypair first. Only if that succeeds
do we replace the main keystore. On either local-disk failure we leave the
staging file intact and print a recovery command.

On any non-200 / network error the staging file is removed — there's no
rotation to recover from.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_ENDPOINT = "https://robotregistryfoundation.org/v2/robots"


def _archive_dir() -> Path:
    """Return the archive directory path, honouring the current HOME."""
    return Path.home() / ".robot-md" / "keys" / "archive"


def _new_staging_path(rrn: str) -> Path:
    """Recovery-staging location for the freshly-generated keypair.

    Written before the rotate POST so that if the canonical keystore write
    fails after the server has accepted the rotation, the operator has a
    real file to recover from.
    """
    return Path.home() / ".robot-md" / "keys" / f"{rrn}.NEW.signing.json"


def _write_secret_file(path: Path, content: str) -> None:
    """Atomically write secret content to path, mode 0600 from the start.

    - Parent dir is created with mode 0o700 if missing.
    - Temp file is created with O_CREAT|O_WRONLY|O_EXCL and mode 0o600, so
      there is no window where the file is world-readable.
    - Temp file is removed on failure so we never leave a stray copy of
      secret material on disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Clear any stale tmp from a prior crashed invocation so O_EXCL succeeds.
    with contextlib.suppress(FileNotFoundError):
        tmp.unlink()
    fd = os.open(str(tmp), os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        tmp.replace(path)
    except OSError:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


def _silent_unlink(path: Path) -> None:
    """Remove a file if it exists; swallow errors (best-effort cleanup)."""
    with contextlib.suppress(FileNotFoundError, OSError):
        path.unlink()


def _serialize_keypair(rrn: str, kp) -> dict:
    """Serialize a SigningKeypair to the same JSON shape as save_keypair.

    Inlined from signing.save_keypair to allow writing to an arbitrary path
    (save_keypair always writes to the canonical keystore location).
    """
    from datetime import datetime, timezone

    return {
        "rrn": rrn,
        "pq_kid": kp.pq_kid,
        "ml_dsa": {
            "pub": base64.b64encode(kp.ml_dsa.public_key_bytes).decode(),
            "sec": base64.b64encode(kp.ml_dsa._secret_key).decode(),
        },
        "ed25519": {
            "pub": base64.b64encode(kp.ed25519_pub).decode(),
            "sec": base64.b64encode(kp.ed25519_sec).decode(),
        },
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def archive_old_keypair(rrn: str, old_kp) -> Path:
    """Write old keypair JSON to archive dir, mode 0600. Write-to-tmp-then-rename.

    Returns the path to the archive file.

    Raises OSError if any I/O step fails. The caller must handle this and
    leave the main keystore untouched if this raises.
    """
    from robot_md.signing import kid_from_pub

    old_kid = kid_from_pub(old_kp.ml_dsa.public_key_bytes)
    dest = _archive_dir() / f"{rrn}.{old_kid}.signing.json"
    blob = _serialize_keypair(rrn, old_kp)
    _write_secret_file(dest, json.dumps(blob, indent=2))
    return dest


def build_rotate_request(old_kp, new_kp, rrn: str) -> dict[str, Any]:
    """Build the dual-signed rotation request body.

    Both envelopes sign the same canonical dict (rrn, action, new key info),
    but one is stamped with the old key's pq_signing_pub/pq_kid/sig and the
    other with the new key's pq_signing_pub/pq_kid/sig. RRF verifies both to
    confirm the old key authorises the rotation and the new key is live.
    """
    from robot_md.signing import kid_from_pub, sign_body

    new_pub_b64 = base64.b64encode(new_kp.ml_dsa.public_key_bytes).decode("ascii")
    new_kid = kid_from_pub(new_kp.ml_dsa.public_key_bytes)
    canonical: dict[str, Any] = {
        "rrn": rrn,
        "action": "rotate",
        "new_pq_signing_pub": new_pub_b64,
        "new_pq_kid": new_kid,
    }
    return {
        "by_old_key": sign_body(old_kp, canonical),
        "by_new_key": sign_body(new_kp, canonical),
    }


def post_rotate(
    url: str, body: dict[str, Any], *, timeout: float = 15.0
) -> tuple[int, str]:
    """POST body as JSON to url.

    Returns (status_code, response_text) on HTTP responses.
    For network errors (URLError) returns (0, reason_str) as a sentinel.

    NOTE: HTTPError must be caught before URLError because HTTPError is a
    subclass of URLError.
    """
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "robot-md-cli/0.9 (+https://robotmd.dev)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
            return resp.status, text
    except urllib.error.HTTPError as e:
        err_text = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        return e.code, err_text
    except urllib.error.URLError as e:
        return 0, str(e.reason)


def _extract_error(text: str) -> str:
    """Try to extract an 'error' field from a JSON body; fall back to raw text."""
    try:
        obj = json.loads(text)
        return obj.get("error", text.strip()[:200])
    except (json.JSONDecodeError, AttributeError):
        return text.strip()[:200]


def cli_rotate_key(
    rrn: str,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
) -> int:
    """Rotate the signing key for ``rrn`` at ``endpoint``.

    Returns exit code:
        0   — success
        1   — pre-flight or server/network failure (keystore untouched)
        2   — server accepted but archive-write failed (keystore still has old key)
    """
    from robot_md.signing import generate_keypair, load_keypair, save_keypair

    old_kp = load_keypair(rrn)
    if old_kp is None:
        print(
            f"No signing key for {rrn}; cannot rotate. "
            "Did you register with a v0.9.1+ client?",
            file=sys.stderr,
        )
        return 1

    new_kp = generate_keypair()

    # Persist new_kp to a recovery staging file BEFORE the POST so that any
    # local-disk failure after the server has accepted the rotation leaves the
    # operator with real key material to recover from (not just an in-memory
    # keypair that's about to be garbage-collected).
    staging_path = _new_staging_path(rrn)
    try:
        new_blob = _serialize_keypair(rrn, new_kp)
        _write_secret_file(staging_path, json.dumps(new_blob, indent=2))
    except OSError as e:
        print(
            f"Could not stage new keypair for recovery at {staging_path}: {e}",
            file=sys.stderr,
        )
        return 1

    req_body = build_rotate_request(old_kp, new_kp, rrn)
    url = f"{endpoint.rstrip('/')}/{rrn}/rotate-key"
    status, text = post_rotate(url, req_body)

    # Network error sentinel
    if status == 0:
        # Server never accepted; staging is pure waste and would confuse a
        # future invocation. Remove it.
        _silent_unlink(staging_path)
        print(f"Could not reach {url}: {text}", file=sys.stderr)
        return 1

    if status != 200:
        # Server rejected; same reasoning — no rotation to recover from.
        _silent_unlink(staging_path)
        error_msg = _extract_error(text)
        if status == 400:
            print(f"RRF rejected rotate: {error_msg}", file=sys.stderr)
        elif status == 401:
            print(f"Signature rejected by RRF: {error_msg}", file=sys.stderr)
        elif status == 403:
            print(f"Record is revoked: {rrn}", file=sys.stderr)
        elif status == 404:
            print(f"RRN not found at {endpoint}", file=sys.stderr)
        else:
            print(f"RRF returned {status}: {text.strip()[:500]}", file=sys.stderr)
        return 1

    # Server accepted (200). From here on, exit-2 paths MUST leave the staging
    # file in place so the operator has recoverable key material.

    # Archive old key FIRST — if this fails the old key is still in the
    # keystore, which is the safest recovery state.
    try:
        archive_dest = archive_old_keypair(rrn, old_kp)
    except OSError as e:
        print(
            f"Server rotated but archive-write failed: {e}. "
            "Local keystore still has old key.",
            file=sys.stderr,
        )
        print(
            "Rotation is server-side complete; the server now expects the new key. "
            f"Recover by copying the staged new keypair into place:\n"
            f"    mv {staging_path} {Path.home() / '.robot-md' / 'keys' / (rrn + '.signing.json')}",
            file=sys.stderr,
        )
        return 2

    # Archive succeeded — now atomically replace the keystore.
    try:
        save_keypair(rrn, new_kp)
    except OSError as e:
        print(
            f"Server rotated and archive written, but keystore save failed: {e}. "
            f"Archive at {archive_dest} holds the old key.",
            file=sys.stderr,
        )
        print(
            "Rotation is server-side complete; the server now expects the new key. "
            f"Recover by copying the staged new keypair into place:\n"
            f"    mv {staging_path} {Path.home() / '.robot-md' / 'keys' / (rrn + '.signing.json')}",
            file=sys.stderr,
        )
        return 2

    # Happy path: keystore now has new key, archive has old key. Staging is
    # redundant; clean it up so future invocations don't trip over it.
    _silent_unlink(staging_path)
    print(
        f"Rotated. Old key archived at {archive_dest} "
        "(treat as backup credential — can still revoke if new key is lost)."
    )
    return 0
