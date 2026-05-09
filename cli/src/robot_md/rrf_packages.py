"""RRF /v2/packages HTTP client.

Wraps the 6 endpoints with typed Python entry points + custom exceptions.
All requests carry an explicit User-Agent (Cloudflare blocks default urllib UA;
see feedback_cloudflare_blocks_default_urllib_ua.md).
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

RRF_PACKAGES_BASE = "https://robotregistryfoundation.org/v2/packages"
USER_AGENT = "robot-md/cli (+https://robotmd.dev)"


class PackageNotFoundError(Exception):
    """Raised when an RPN does not exist at RRF (404)."""


class PackageConflictError(Exception):
    """Raised when a name is already taken (409 on register)."""


class SignatureError(Exception):
    """Raised when RRF rejects the request body (400)."""


class NetworkError(Exception):
    """Raised when the HTTP layer fails before getting a response."""


def _post(url: str, signed_body: dict, *, timeout: float = 10.0) -> dict:
    data = json.dumps(signed_body).encode()
    req = Request(
        url,
        data=data,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        if e.code == 404:
            raise PackageNotFoundError(url) from e
        if e.code == 409:
            raise PackageConflictError(url) from e
        if e.code == 400:
            raise SignatureError(f"{url}: {e.reason}") from e
        raise NetworkError(f"{url}: HTTP {e.code} {e.reason}") from e
    except URLError as e:
        raise NetworkError(f"{url}: {e.reason}") from e


def _get(url: str, *, timeout: float = 10.0) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        if e.code == 404:
            raise PackageNotFoundError(url) from e
        raise NetworkError(f"{url}: HTTP {e.code} {e.reason}") from e
    except URLError as e:
        raise NetworkError(f"{url}: {e.reason}") from e


def register_package(*, signed_body: dict, timeout: float = 10.0) -> dict:
    """First publish: POST /v2/packages/register. Returns {rpn, registered_at, record_url}."""
    return _post(f"{RRF_PACKAGES_BASE}/register", signed_body, timeout=timeout)


def append_version(rpn: str, *, signed_body: dict, timeout: float = 10.0) -> dict:
    """POST /v2/packages/[rpn]/versions. Returns updated record."""
    return _post(f"{RRF_PACKAGES_BASE}/{rpn}/versions", signed_body, timeout=timeout)


def fetch_one(rpn: str, *, timeout: float = 10.0) -> dict:
    """GET /v2/packages/[rpn]. Returns full record."""
    return _get(f"{RRF_PACKAGES_BASE}/{rpn}", timeout=timeout)


def list_packages(
    *,
    type_filter: str = "actuator",
    tag: str | None = None,
    include_revoked: bool = False,
    limit: int = 100,
    cursor: str | None = None,
    timeout: float = 10.0,
) -> dict:
    """GET /v2/packages with filters. Returns {packages: [...], next_cursor?}."""
    qs = {"type": type_filter, "limit": str(limit)}
    if tag:
        qs["tag"] = tag
    if include_revoked:
        qs["include_revoked"] = "1"
    if cursor:
        qs["cursor"] = cursor
    return _get(f"{RRF_PACKAGES_BASE}?{urlencode(qs)}", timeout=timeout)


def revoke_package(rpn: str, *, signed_body: dict, timeout: float = 10.0) -> dict:
    """POST /v2/packages/[rpn]/revoke. Returns updated record."""
    return _post(f"{RRF_PACKAGES_BASE}/{rpn}/revoke", signed_body, timeout=timeout)


def transfer_package(rpn: str, *, signed_body: dict, timeout: float = 10.0) -> dict:
    """POST /v2/packages/[rpn]/transfer. Returns updated record."""
    return _post(f"{RRF_PACKAGES_BASE}/{rpn}/transfer", signed_body, timeout=timeout)
