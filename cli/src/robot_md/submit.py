"""Submit signed artifacts to RRF v2 (P2.1).

Single helper that POSTs an emitted artifact to the matching RRF endpoint,
records the submission in the local audit log (audit.py), and returns the
parsed response. Bearer-authed with the apikey from
~/.robot-md/keys/<rrn>.apikey (or supplied explicitly).

Wire path mapping:
- fria             → /v2/robots/<rrn>/fria
- ifu              → /v2/robots/<rrn>/ifu
- safety-benchmark → /v2/robots/<rrn>/safety-benchmark
- incident-report  → /v2/robots/<rrn>/incident-report
- eu-register      → /v2/robots/<rrn>/eu-register
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from robot_md import __version__
from robot_md.audit import record_event
from robot_md.register import load_apikey

DEFAULT_RRF_ENDPOINT = "https://robotregistryfoundation.org"

SUPPORTED_KINDS: tuple[str, ...] = (
    "fria",
    "ifu",
    "safety-benchmark",
    "incident-report",
    "eu-register",
)


class SubmitError(RuntimeError):
    """Raised on validation failures or non-2xx HTTP responses."""


def _build_url(endpoint: str, rrn: str, kind: str) -> str:
    base = endpoint.rstrip("/")
    if base.endswith("/v2/robots"):
        return f"{base}/{rrn}/{kind}"
    return f"{base}/v2/robots/{rrn}/{kind}"


def submit_artifact(
    artifact: dict[str, Any],
    *,
    rrn: str,
    kind: str,
    endpoint: str = DEFAULT_RRF_ENDPOINT,
    api_key: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """POST `artifact` to RRF /v2/robots/<rrn>/<kind>. Audit-records on every outcome.

    Returns ``{"status": int, "body": dict}``. Raises SubmitError on
    missing apikey, unsupported kind, or any non-2xx HTTP response —
    the failure path also records to the audit log so the operator has
    a tamper-evident trail of attempts.
    """
    if kind not in SUPPORTED_KINDS:
        raise SubmitError(
            f"unsupported kind {kind!r}; expected one of {', '.join(SUPPORTED_KINDS)}"
        )

    if api_key is None:
        api_key = load_apikey(rrn)
    if not api_key:
        raise SubmitError(
            f"no apikey for {rrn} in ~/.robot-md/keys/. Pass --api-key, "
            f"or run `robot-md register` to mint one."
        )

    url = _build_url(endpoint, rrn, kind)
    payload = json.dumps(artifact).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
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
            event="submission",
            details={
                "kind": kind,
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
            event="submission",
            details={
                "kind": kind,
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
        event="submission",
        details={
            "kind": kind,
            "endpoint": url,
            "status": status,
            "outcome": "ok",
        },
    )

    return {"status": status, "body": body}
