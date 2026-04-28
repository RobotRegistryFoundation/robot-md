"""Submit signed artifacts to RRF v2 (P2.1).

Single helper that POSTs an emitted artifact to the matching RRF endpoint,
records the submission in the local audit log (audit.py), and returns the
parsed response.

Wire path mapping (per kind):
- fria             → POST /v2/robots/<rrn>/fria              (Bearer-auth via apikey)
- ifu              → POST /v2/robots/<rrn>/ifu               (Bearer-auth via apikey)
- safety-benchmark → POST /v2/robots/<rrn>/safety-benchmark  (Bearer-auth via apikey)
- incident-report  → POST /v2/robots/<rrn>/incident-report   (Bearer-auth via apikey)
- eu-register      → POST /v2/models/<rmn>/eu-register       (signed-body auth; NO bearer)

Per Art. 49 of the EU AI Act, eu-register is scoped per AI system (per
model), so it routes through the model namespace using the RMN from the
signed artifact. Submitter ownership is derived from the signed payload,
not the bearer apikey (RRF: functions/v2/models/[rmn]/eu-register.ts).

Audit log is always keyed by `rrn` regardless of kind — that is the robot
that produced the artifact.
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

# kind → URL template + auth requirements. {id} is filled with rrn or rmn
# depending on the "id" field. "bearer": True → Authorization: Bearer apikey.
KIND_REGISTRY: dict[str, dict[str, Any]] = {
    "fria":             {"id": "rrn", "path": "/v2/robots/{id}/fria",             "bearer": True},
    "ifu":              {"id": "rrn", "path": "/v2/robots/{id}/ifu",              "bearer": True},
    "safety-benchmark": {"id": "rrn", "path": "/v2/robots/{id}/safety-benchmark", "bearer": True},
    "incident-report":  {"id": "rrn", "path": "/v2/robots/{id}/incident-report",  "bearer": True},
    "eu-register":      {"id": "rmn", "path": "/v2/models/{id}/eu-register",      "bearer": False},
}
SUPPORTED_KINDS: tuple[str, ...] = tuple(KIND_REGISTRY.keys())


class SubmitError(RuntimeError):
    """Raised on validation failures or non-2xx HTTP responses."""


def _build_url(endpoint: str, kind: str, subject_id: str) -> str:
    base = endpoint.rstrip("/")
    return base + KIND_REGISTRY[kind]["path"].format(id=subject_id)


def submit_artifact(
    artifact: dict[str, Any],
    *,
    rrn: str,
    kind: str,
    rmn: str | None = None,
    endpoint: str = DEFAULT_RRF_ENDPOINT,
    api_key: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """POST `artifact` to the kind-specific RRF endpoint. Audit-records on every outcome.

    Returns ``{"status": int, "body": dict}``. Raises SubmitError on
    missing required ID, missing apikey (when bearer-required), unsupported
    kind, or any non-2xx HTTP response — the failure path also records to
    the audit log so the operator has a tamper-evident trail of attempts.

    For kind="eu-register" the URL is /v2/models/<rmn>/eu-register and
    no Bearer header is sent (RRF derives the submitter from the signed
    payload). Caller MUST pass rmn= for that kind; the rrn is still
    required for audit logging.
    """
    if kind not in KIND_REGISTRY:
        raise SubmitError(
            f"unsupported kind {kind!r}; expected one of {', '.join(SUPPORTED_KINDS)}"
        )

    spec = KIND_REGISTRY[kind]
    subject_id = rrn if spec["id"] == "rrn" else rmn
    if not subject_id:
        raise SubmitError(
            f"kind={kind!r} requires {spec['id']}; "
            f"call submit_artifact(..., {spec['id']}=<value>)."
        )

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": f"robot-md/{__version__}",
    }

    if spec["bearer"]:
        if api_key is None:
            api_key = load_apikey(rrn)
        if not api_key:
            raise SubmitError(
                f"no apikey for {rrn} in ~/.robot-md/keys/. Pass --api-key, "
                f"or run `robot-md register` to mint one."
            )
        headers["Authorization"] = f"Bearer {api_key}"

    url = _build_url(endpoint, kind, subject_id)
    payload = json.dumps(artifact).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        headers=headers,
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
