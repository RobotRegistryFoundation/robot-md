"""ROBOT.md provenance-footer signing (the producer side).

robot-md-gateway only actuates against a manifest that carries a provenance
signature footer:

    <!-- ROBOT-MD-SIG kid=<kid> sig=<base64> -->

signed by an *operator* key whose public half resolves at RRF `/v2/keys/<kid>`.
The gateway verifies it in `robot_md_gateway.manifest_provenance.verify_manifest`,
where the signed pre-image is the file content up to (but not including) the
newline that immediately precedes the footer comment.

This module produces a footer that satisfies that verifier exactly. Keep the
pre-image construction here in lock-step with the gateway's `_SIG_RE` /
`body = text[: match.start()]`.
"""

from __future__ import annotations

import base64
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# Must match robot_md_gateway.manifest_provenance._SIG_RE byte-for-byte.
_SIG_RE = re.compile(
    r"\n<!--\s*ROBOT-MD-SIG\s+kid=(?P<kid>\S+)\s+sig=(?P<sig>[A-Za-z0-9+/=]+)\s*-->\s*\Z",
)


def strip_footer(text: str) -> str:
    """Return `text` with any trailing ROBOT-MD-SIG footer removed.

    Re-signing is idempotent: strip the old footer before signing the body so
    repeated `sign-manifest` runs don't nest footers.
    """
    match = _SIG_RE.search(text)
    return text[: match.start()] if match else text


def signed_manifest_text(text: str, priv: Ed25519PrivateKey, *, kid: str) -> str:
    """Return `text` with a fresh ROBOT-MD-SIG footer, replacing any existing one.

    The Ed25519 signature covers exactly `body` — the manifest content with any
    prior footer stripped and trailing newlines removed — so that the gateway's
    `text[: match.start()]` pre-image matches what we signed here.
    """
    body = strip_footer(text).rstrip("\n")
    sig = base64.b64encode(priv.sign(body.encode("utf-8"))).decode()
    return f"{body}\n<!-- ROBOT-MD-SIG kid={kid} sig={sig} -->\n"


def verify_manifest_text(text: str, pub: Ed25519PublicKey) -> tuple[bool, str]:
    """Verify a signed manifest's footer against `pub`.

    Returns (ok, kid_or_reason). Mirrors the gateway's verifier so callers can
    self-check before writing the file. Does NOT resolve the kid at RRF.
    """
    match = _SIG_RE.search(text)
    if match is None:
        return False, "no ROBOT-MD-SIG footer (signature absent)"
    try:
        pub.verify(base64.b64decode(match.group("sig")), text[: match.start()].encode("utf-8"))
    except InvalidSignature:
        return False, "signature did not verify against the body"
    return True, match.group("kid")
