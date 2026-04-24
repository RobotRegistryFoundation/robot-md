"""`robot-md revoke-key` — revoke a robot's signing key at the Robot Registry Foundation.

After revocation all §22-26 compliance intakes for this RRN are refused with 403.
This is a ONE-WAY operation.

Usage via CLI:

    robot-md revoke-key RRN-000000000042
    robot-md revoke-key RRN-000000000042 --reason "decommissioned"
    robot-md revoke-key RRN-000000000042 --endpoint https://staging.rrf...

Exit codes: 0 success or already-revoked (409), non-zero on any failure.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_ENDPOINT = "https://robotregistryfoundation.org/v2/robots"


def build_revoke_body(rrn: str, reason: str | None) -> dict[str, Any]:
    """Build the pre-signing revoke request body.

    The 'reason' key is OMITTED entirely when not provided — the server
    rejects non-string reason values so we must not send ``reason: None``.
    """
    body: dict[str, Any] = {"rrn": rrn, "action": "revoke"}
    if reason is not None:
        body["reason"] = reason
    return body


def post_revoke(
    url: str, signed_body: dict[str, Any], *, timeout: float = 15.0
) -> tuple[int, str]:
    """POST signed_body as JSON to url.

    Returns (status_code, response_text) on HTTP responses.
    For network errors (URLError) returns (0, reason_str) as a sentinel.

    NOTE: HTTPError must be caught before URLError because HTTPError is a
    subclass of URLError.
    """
    data = json.dumps(signed_body).encode("utf-8")
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


def cli_revoke_key(
    rrn: str,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    reason: str | None = None,
) -> int:
    """Revoke the signing key for ``rrn`` at ``endpoint``.

    Returns exit code. 0 = success (204) or already-revoked (409).
    Non-zero = any other failure.
    """
    from robot_md.signing import load_keypair, sign_body

    kp = load_keypair(rrn)
    if kp is None:
        print(
            f"No signing key for {rrn} at ~/.robot-md/keys/{rrn}.signing.json; "
            "did you register with a v0.9.1+ client?",
            file=sys.stderr,
        )
        return 1

    body = build_revoke_body(rrn, reason)
    signed = sign_body(kp, body)
    url = f"{endpoint.rstrip('/')}/{rrn}/revoke-key"
    status, text = post_revoke(url, signed)

    # Network error sentinel
    if status == 0:
        print(f"Could not reach {url}: {text}", file=sys.stderr)
        return 1

    if status == 204:
        print(f"Revoked: {rrn}")
        return 0

    if status == 409:
        print(f"Already revoked: {rrn}")
        return 0

    if status == 401:
        # Try to extract error message from JSON body
        try:
            obj = json.loads(text)
            error_msg = obj.get("error", text.strip()[:200])
        except (json.JSONDecodeError, AttributeError):
            error_msg = text.strip()[:200]
        print(f"Signature rejected by RRF: {error_msg}", file=sys.stderr)
        return 1

    if status == 404:
        # Include the server body excerpt so the operator can tell a wrong
        # --endpoint apart from a missing registration.
        body_excerpt = text.strip()[:200] if text else ""
        suffix = f": {body_excerpt}" if body_excerpt else ""
        print(f"RRN not found at {endpoint}{suffix}", file=sys.stderr)
        return 1

    # All other non-2xx
    print(f"RRF returned {status}: {text.strip()[:500]}", file=sys.stderr)
    return 1
