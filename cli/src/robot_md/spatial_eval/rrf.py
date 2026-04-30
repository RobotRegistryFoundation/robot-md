"""SP6 Phase 1.5 — RRF §27 client for spatial-eval Score JSON submission.

Parallel urllib helper alongside `robot_md.submit`; the §27 path scheme
is run-id keyed (`/v1/spatial-eval/runs`) rather than robot-keyed
(`/v2/robots/{rrn}/...`), so KIND_REGISTRY in submit.py generalizes
poorly to it. Audit logging via `robot_md.audit.record_event` is
preserved identically.

Wire-format contract is locked in
docs/superpowers/specs/2026-04-26-sp6-spatial-intelligence-eval-design.md
"§27 wire format" subsection. RRF backend implementation must mirror.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from robot_md import __version__
from robot_md.audit import record_event
from robot_md.register import load_apikey
from robot_md.spatial_eval.score import ScoreJSON

DEFAULT_RRF_ENDPOINT = "https://robotregistryfoundation.org"
RUNS_PATH = "/v1/spatial-eval/runs"
RUN_DETAIL_PATH = "/v1/spatial-eval/runs/{submission_id}"
SPEC_PATH = "/v1/spatial-eval/spec/{version}"


class RrfSubmitError(RuntimeError):
    """Raised on missing apikey, network failure, or non-2xx HTTP response."""


class RrfFetchError(RuntimeError):
    """Raised when the spec endpoint can't serve the requested data
    (network down, 404, malformed response). Verifiers should treat this
    as a soft failure — fall back to self-attested rather than raising.
    """


def fetch_rrf_pubkey(
    spec_version: str,
    *,
    endpoint: str = DEFAULT_RRF_ENDPOINT,
    timeout: float = 5.0,
) -> bytes:
    """GET /v1/spatial-eval/spec/{version} and return the raw RRF ML-DSA
    public key bytes (base64-decoded). Raises RrfFetchError on any
    non-success path.

    No audit logging here — pubkey fetches are read-only and frequent;
    spamming the audit chain with every verify call would be noise.
    """
    import base64
    import binascii

    url = endpoint.rstrip("/") + SPEC_PATH.format(version=spec_version)
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": f"robot-md/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body_bytes = resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        raise RrfFetchError(f"could not fetch RRF spec from {url}: {e}") from e

    try:
        body = json.loads(body_bytes)
    except json.JSONDecodeError as e:
        raise RrfFetchError(f"RRF spec returned non-JSON: {e}") from e

    pubkey_b64 = body.get("rrf_pubkey")
    if not isinstance(pubkey_b64, str) or not pubkey_b64:
        raise RrfFetchError(f"RRF spec response missing rrf_pubkey: {body!r}")
    try:
        return base64.b64decode(pubkey_b64)
    except (ValueError, binascii.Error) as e:
        raise RrfFetchError(f"RRF spec rrf_pubkey is not valid base64: {e}") from e


def submit_score(
    score: ScoreJSON,
    *,
    endpoint: str = DEFAULT_RRF_ENDPOINT,
    api_key: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """POST a self-attested ScoreJSON to /v1/spatial-eval/runs.

    Returns the parsed response body (containing `submission_id` +
    `status`, plus a counter-signed `score` on the sync 200 path). Raises
    RrfSubmitError on missing apikey, network failure, or non-2xx HTTP.
    Records an audit entry on every outcome for the robot's RRN.
    """
    rrn = score.rrn

    if api_key is None:
        api_key = load_apikey(rrn)
    if not api_key:
        raise RrfSubmitError(
            f"no apikey for {rrn} in ~/.robot-md/keys/. Run `robot-md register` to mint one."
        )

    url = endpoint.rstrip("/") + RUNS_PATH
    body = {"score": score.to_dict()}
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"robot-md/{__version__}",
            "Authorization": f"Bearer {api_key}",
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
                "kind": "spatial-eval-run",
                "endpoint": url,
                "status": e.code,
                "outcome": "failed",
                "error": body_bytes.decode("utf-8", errors="replace")[:500],
            },
        )
        raise RrfSubmitError(f"RRF {url} returned {e.code}: {body_bytes[:200]!r}") from e
    except urllib.error.URLError as e:
        record_event(
            rrn,
            event="submission",
            details={
                "kind": "spatial-eval-run",
                "endpoint": url,
                "outcome": "network_error",
                "error": str(e.reason),
            },
        )
        raise RrfSubmitError(f"could not reach {url}: {e.reason}") from e

    try:
        parsed = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        parsed = {"_raw": body_bytes.decode("utf-8", errors="replace")[:500]}

    record_event(
        rrn,
        event="submission",
        details={
            "kind": "spatial-eval-run",
            "endpoint": url,
            "status": status,
            "outcome": "ok",
        },
    )

    return parsed


def poll_status(
    submission_id: str,
    *,
    rrn: str,
    endpoint: str = DEFAULT_RRF_ENDPOINT,
    api_key: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """GET /v1/spatial-eval/runs/{submission_id}.

    Returns the parsed response body. Status will be one of `pending`,
    `counter_signed`, or `rejected`; on `counter_signed` the body
    includes `score` with `rrf_signature` populated. Audit entry is
    recorded under kind=`spatial-eval-poll`.
    """
    if api_key is None:
        api_key = load_apikey(rrn)
    if not api_key:
        raise RrfSubmitError(
            f"no apikey for {rrn} in ~/.robot-md/keys/. Run `robot-md register` to mint one."
        )

    url = endpoint.rstrip("/") + RUN_DETAIL_PATH.format(submission_id=submission_id)
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": f"robot-md/{__version__}",
            "Authorization": f"Bearer {api_key}",
        },
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
                "kind": "spatial-eval-poll",
                "endpoint": url,
                "status": e.code,
                "outcome": "failed",
                "error": body_bytes.decode("utf-8", errors="replace")[:500],
            },
        )
        raise RrfSubmitError(f"RRF {url} returned {e.code}: {body_bytes[:200]!r}") from e
    except urllib.error.URLError as e:
        record_event(
            rrn,
            event="submission",
            details={
                "kind": "spatial-eval-poll",
                "endpoint": url,
                "outcome": "network_error",
                "error": str(e.reason),
            },
        )
        raise RrfSubmitError(f"could not reach {url}: {e.reason}") from e

    try:
        parsed = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        parsed = {"_raw": body_bytes.decode("utf-8", errors="replace")[:500]}

    record_event(
        rrn,
        event="submission",
        details={
            "kind": "spatial-eval-poll",
            "endpoint": url,
            "status": status,
            "outcome": "ok",
        },
    )

    return parsed
