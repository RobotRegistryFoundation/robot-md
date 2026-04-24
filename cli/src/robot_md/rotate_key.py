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
    2   — partial failure: server accepted BUT archive-write failed.
          The server now expects the NEW key, but the local keystore still
          has the OLD key. The operator must recover manually (see error
          message printed to stderr). Re-running rotate-key will fail
          because the server's current key is now the new one.

Critical ordering constraint
----------------------------
The archive-write MUST succeed BEFORE the keystore replace. If the archive
write fails (disk full, permissions), we bail out with exit code 2 and leave
the old key in the keystore. The operator is instructed to contact support or
manually recover by saving the new keypair to the keystore path.

Failure modes:
- Step 1 (archive) fails: old keystore is still valid; re-run revoke-key with
  the old key to revoke if needed.
- Step 2 (keystore replace) fails after step 1 succeeded: old key is in the
  archive; new key is lost. Operator must manually copy archive → keystore.
"""

from __future__ import annotations

import base64
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
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    blob = _serialize_keypair(rrn, old_kp)
    tmp.write_text(json.dumps(blob, indent=2))
    os.chmod(tmp, 0o600)
    tmp.replace(dest)
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
    req_body = build_rotate_request(old_kp, new_kp, rrn)
    url = f"{endpoint.rstrip('/')}/{rrn}/rotate-key"
    status, text = post_rotate(url, req_body)

    # Network error sentinel
    if status == 0:
        print(f"Could not reach {url}: {text}", file=sys.stderr)
        return 1

    if status != 200:
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

    # Server accepted (200). Archive old key FIRST — if this fails the old
    # key is still in the keystore, which is the safest recovery state.
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
            "Recover by manually saving the new keypair to "
            f"~/.robot-md/keys/{rrn}.signing.json, or contact support.",
            file=sys.stderr,
        )
        return 2  # distinct non-zero code for this partial-failure mode

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
            "Recover by manually saving the new keypair to "
            f"~/.robot-md/keys/{rrn}.signing.json, or contact support.",
            file=sys.stderr,
        )
        return 2

    print(
        f"Rotated. Old key archived at {archive_dest} "
        "(treat as backup credential — can still revoke if new key is lost)."
    )
    return 0
