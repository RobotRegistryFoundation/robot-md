"""`robot-md verify-tier` — promote a robot's verification_status at the Robot Registry Foundation.

Supports promotion to manufacturer_claimed (DNS TXT proof) and
manufacturer_verified (DNS TXT + RURI /.well-known/rcan-manifest.json + signed attestation).

Community tier is maintainer-curated via PR and cannot be promoted via this API.

Usage via CLI:

    robot-md verify-tier RRN-000000000042 \\
        --target manufacturer_claimed \\
        --dns-domain robotis.com

    robot-md verify-tier RRN-000000000042 \\
        --target manufacturer_verified \\
        --dns-domain robotis.com \\
        --ruri https://robotis.com \\
        --attestation-file signed_attestation.json

Exit codes: 0 success, non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_ENDPOINT = "https://robotregistryfoundation.org/v2/robots"

VALID_TARGETS = {"manufacturer_claimed", "manufacturer_verified"}

# Hard cap on attestation payload size. Attestations are signed JSON blobs
# holding a public key + a few digests — a sane real one is well under 10 KiB.
# The cap guards against operator mistakes (pointing at a log file) and
# adversarial input.
MAX_ATTESTATION_BYTES = 1 * 1024 * 1024  # 1 MiB


def _is_interactive() -> bool:
    if os.environ.get("ROBOT_MD_NONINTERACTIVE") == "1":
        return False
    return sys.stdin.isatty()


def _preflight_message(rrn: str, target: str, dns_domain: str, ruri: str | None) -> str:
    msg = [
        f"About to request tier promotion for {rrn} to {target}.",
        "",
        "Before continuing, ensure this DNS TXT record exists:",
        f'  _rcan-verify.{dns_domain}  TXT  "rrn={rrn};model=<your-model>"',
    ]
    if target == "manufacturer_verified":
        msg += [
            "",
            f"Also ensure {ruri}/.well-known/rcan-manifest.json returns a JSON object",
            f"with rrn={rrn} (RRF will fetch it during promotion).",
        ]
    msg += ["", "RRF will refuse promotion if any check fails.", ""]
    return "\n".join(msg)


def build_verify_tier_body(
    rrn: str,
    target: str,
    dns_domain: str,
    ruri: str | None,
    attestation: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the pre-signing verify-tier request body."""
    body: dict[str, Any] = {
        "rrn": rrn,
        "action": "verify-tier",
        "target_tier": target,
        "binding": {"type": "dns-txt", "value": dns_domain},
    }
    if target == "manufacturer_verified":
        body["ruri"] = ruri
        body["attestation"] = attestation
    return body


def post_verify_tier(
    url: str, signed_body: dict[str, Any], *, timeout: float = 30.0
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
            "User-Agent": "robot-md-cli/1.0 (+https://robotmd.dev)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return resp.status, text
    except urllib.error.HTTPError as e:
        err_text = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        return e.code, err_text
    except urllib.error.URLError as e:
        return 0, str(e.reason)


def _extract_error(text: str) -> str:
    try:
        return json.loads(text).get("error", text[:200])
    except (json.JSONDecodeError, AttributeError, TypeError):
        return text[:200]


def cli_verify_tier(
    rrn: str,
    *,
    target: str,
    dns_domain: str,
    ruri: str | None = None,
    attestation_file: Path | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
    non_interactive: bool = False,
) -> int:
    """Promote the verification_status for ``rrn`` at ``endpoint``.

    Returns exit code. 0 = success. Non-zero = any failure.
    """
    # 1. target validation
    if target == "community":
        print(
            "community tier is maintainer-curated via PR, not promotable via API.",
            file=sys.stderr,
        )
        return 1
    if target not in VALID_TARGETS:
        print(f"Unknown target_tier: {target}", file=sys.stderr)
        return 1

    # 2. manufacturer_verified requires ruri + attestation_file
    attestation: dict[str, Any] | None = None
    if target == "manufacturer_verified":
        if ruri is None or attestation_file is None:
            print(
                "manufacturer_verified requires --ruri and --attestation-file",
                file=sys.stderr,
            )
            return 1
        if not attestation_file.exists():
            print(f"Attestation file not found: {attestation_file}", file=sys.stderr)
            return 1
        try:
            size = attestation_file.stat().st_size
        except OSError as e:
            print(f"Could not stat attestation file: {e}", file=sys.stderr)
            return 1
        if size > MAX_ATTESTATION_BYTES:
            print(
                f"Attestation file too large: {size} bytes (max {MAX_ATTESTATION_BYTES} = 1 MiB)",
                file=sys.stderr,
            )
            return 1
        try:
            raw = attestation_file.read_text()
        except OSError as e:
            print(f"Could not read attestation file: {e}", file=sys.stderr)
            return 1
        try:
            attestation = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"Attestation file is not valid JSON: {e}", file=sys.stderr)
            return 1
        if not isinstance(attestation, dict):
            print("Attestation file must contain a JSON object", file=sys.stderr)
            return 1

    # 3. load signing keypair
    from robot_md.signing import load_keypair, sign_body

    kp = load_keypair(rrn)
    if kp is None:
        print(
            f"No signing key for {rrn} at ~/.robot-md/keys/{rrn}.signing.json",
            file=sys.stderr,
        )
        return 1

    # 4. pre-flight prompt (skippable)
    if not non_interactive and _is_interactive():
        print(_preflight_message(rrn, target, dns_domain, ruri))
        try:
            input("Press Enter to continue, or Ctrl-C to cancel... ")
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.", file=sys.stderr)
            return 1

    # 5. build + sign + post
    body = build_verify_tier_body(rrn, target, dns_domain, ruri, attestation)
    signed = sign_body(kp, body)
    url = f"{endpoint.rstrip('/')}/{rrn}/verify-tier"
    status, text = post_verify_tier(url, signed)

    # 6. response handling
    if status == 200:
        try:
            data = json.loads(text)
            new_status = data.get("verification_status", target)
            print(f"Promoted {rrn} to {new_status}.")
            binding = data.get("identity_binding", {})
            print(f"identity_binding: {json.dumps(binding, indent=2)}")
        except json.JSONDecodeError:
            print(f"Promoted {rrn} to {target}. (Response was not JSON: {text[:200]})")
        return 0

    if status == 400:
        print(f"RRF rejected: {_extract_error(text)}", file=sys.stderr)
        return 1

    if status == 401:
        print(f"Signature rejected by RRF: {_extract_error(text)}", file=sys.stderr)
        return 1

    if status == 403:
        print(f"Record is revoked: {rrn}", file=sys.stderr)
        return 1

    if status == 404:
        print(f"RRN not found at {endpoint}: {rrn}", file=sys.stderr)
        return 1

    if status == 409:
        print(f"Promotion state conflict: {_extract_error(text)}", file=sys.stderr)
        return 1

    if status == 0:
        print(f"Could not reach {url}: {text}", file=sys.stderr)
        return 1

    print(f"RRF returned {status}: {text[:500]}", file=sys.stderr)
    return 1
