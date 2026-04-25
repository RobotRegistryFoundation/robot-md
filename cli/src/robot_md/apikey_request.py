"""Apikey-reissue request flow for an existing RRN.

When an operator holds the *signing keypair* for an RRN but lost (or
never received) the *apikey* — register-time apikeys are returned once
and not stored server-side in plaintext — they need a way to request a
new one without losing the RRN. The standard `cli_register` path
refuses re-registration on a manifest that already has metadata.rrn.

This module produces a cryptographically-signed reissue request that:
- the operator can submit out-of-band (email RRF support, attach to a
  GitHub issue, hand to a notified body, etc.) until the server-side
  endpoint exists; OR
- the CLI POSTs to ``/v2/robots/<rrn>/apikey-requests`` once that
  endpoint is implemented.

Auth model: signature on canonical body, verified by RRF against the
registered ``pq_signing_pub``. No bearer token — that's the whole
point; the apikey is what we don't have.

Wire shape (rcan-apikey-request-v1):
    {
      "schema": "rcan-apikey-request-v1",
      "rrn": "RRN-...",
      "operation": "reissue" | "new",
      "generated_at": "<iso8601 utc>",
      "nonce": "<uuid4>",        # anti-replay
      "reason": "<optional>",
      "pq_signing_pub": "...",   # added by sign_request
      "pq_kid": "...",           # ditto
      "sig": {...}               # ditto
    }
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from robot_md import __version__
from robot_md.audit import record_event

APIKEY_REQUEST_SCHEMA = "rcan-apikey-request-v1"

VALID_OPERATIONS: tuple[str, ...] = ("reissue", "new")

DEFAULT_RRF_ENDPOINT = "https://robotregistryfoundation.org"


class SubmitError(RuntimeError):
    """Raised on submission failure (network or non-2xx HTTP)."""


def build_request(
    rrn: str,
    *,
    operation: str = "reissue",
    reason: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build an unsigned rcan-apikey-request-v1 dict.

    Operations:
    - ``reissue`` — server should issue a new apikey for the existing RRN
      (typical case: operator lost the original apikey).
    - ``new``     — server should issue an additional apikey alongside any
      existing one (rotation / parallel use case).
    """
    if operation not in VALID_OPERATIONS:
        raise ValueError(f"operation must be one of {VALID_OPERATIONS}, got {operation!r}")
    payload: dict[str, Any] = {
        "schema": APIKEY_REQUEST_SCHEMA,
        "rrn": rrn,
        "operation": operation,
        "generated_at": generated_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "nonce": str(uuid.uuid4()),
    }
    if reason:
        payload["reason"] = reason
    return payload


def sign_request(req: dict, rrn: str) -> dict:
    """Sign the reissue request with the keystore's hybrid keypair.

    Same wire format as register / IFU / FRIA artifacts (sign_body wraps
    the body with pq_signing_pub + pq_kid + sig). RRF verifies against
    the registered pq_signing_pub for `rrn`.
    """
    from robot_md.signing import load_keypair, sign_body

    kp = load_keypair(rrn)
    if kp is None:
        raise RuntimeError(
            f"no signing keypair for {rrn} at ~/.robot-md/keys/. "
            f"This RRN was either never registered, registered through a "
            f"path that didn't save signing material, or the keystore was "
            f"cleaned up. Without the signing key, RRF cannot authenticate "
            f"a reissue request."
        )
    return sign_body(kp, req)


def submit_request(
    signed: dict,
    *,
    rrn: str,
    endpoint: str = DEFAULT_RRF_ENDPOINT,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """POST a signed reissue request to RRF. Audit-logs every outcome.

    Endpoint defaults to ``{endpoint}/v2/robots/<rrn>/apikey-requests``.
    Note: probed 2026-04-25 — the server-side endpoint does not yet
    exist on robotregistryfoundation.org. Until it does, prefer the
    out-of-band flow (emit signed JSON, hand to RRF support).

    Returns ``{"status": int, "body": dict}``. Raises SubmitError on
    network failure or non-2xx response. Audit log records all attempts.
    """
    base = endpoint.rstrip("/")
    if not base.endswith(f"/v2/robots/{rrn}/apikey-requests"):
        if base.endswith(f"/v2/robots/{rrn}"):
            url = f"{base}/apikey-requests"
        elif base.endswith("/v2/robots"):
            url = f"{base}/{rrn}/apikey-requests"
        else:
            url = f"{base}/v2/robots/{rrn}/apikey-requests"
    else:
        url = base

    payload = json.dumps(signed).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"robot-md/{__version__}",
        },
        data=payload,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body_bytes = resp.read()
    except urllib.error.HTTPError as e:
        body_bytes = e.read() if hasattr(e, "read") else b""
        record_event(
            rrn,
            event="apikey_request",
            details={
                "endpoint": url,
                "status": e.code,
                "outcome": "failed",
                "error": body_bytes.decode("utf-8", errors="replace")[:500],
            },
        )
        raise SubmitError(f"RRF {url} returned {e.code}: {body_bytes[:200]!r}") from e
    except urllib.error.URLError as e:
        record_event(
            rrn,
            event="apikey_request",
            details={
                "endpoint": url,
                "outcome": "network_error",
                "error": str(e.reason),
            },
        )
        raise SubmitError(f"could not reach {url}: {e.reason}") from e

    try:
        body = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        body = {"_raw": body_bytes.decode("utf-8", errors="replace")[:500]}

    record_event(
        rrn,
        event="apikey_request",
        details={
            "endpoint": url,
            "status": status,
            "outcome": "ok",
        },
    )

    return {"status": status, "body": body}
