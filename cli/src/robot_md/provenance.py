"""Manifest provenance footer signing + re-sign/deploy.

The robot-md-gateway verifies a `<!-- ROBOT-MD-SIG kid=<kid> sig=<base64> -->`
footer over the manifest body on EVERY invoke (see
robot_md_gateway.manifest_provenance.verify_manifest). Any command that mutates
the manifest (commission --write, teach, calibrate-vision) therefore invalidates
that footer — the next gateway-routed op would 403 fail-closed. `resign_and_deploy`
regenerates the footer and deploys the freshly-signed file to the gateway's
enforced path so the working copy and the enforced copy never drift.

Signed body (must match the verifier EXACTLY): the manifest text with any existing
footer removed and trailing newlines stripped, signed Ed25519. The file is then
written as `<body>\n<!-- ROBOT-MD-SIG kid=.. sig=.. -->\n`, so the verifier's
`text[:match.start()]` recovers `<body>` verbatim.

NOTE: this signs Ed25519 to match TODAY's gateway verifier. Workstream B5 (crypto
unification) upgrades both signer and verifier to ML-DSA-65 hybrid together.
"""
from __future__ import annotations

import base64
import datetime as dt
import os
import re
import shutil
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519

from robot_md.invoke import rrn_from_ruri
from robot_md.signing import load_keypair

# Must agree with robot_md_gateway.manifest_provenance._SIG_RE.
_SIG_RE = re.compile(
    r"\n<!--\s*ROBOT-MD-SIG\s+kid=(?P<kid>\S+)\s+sig=(?P<sig>[A-Za-z0-9+/=]+)\s*-->\s*\Z",
)

DEFAULT_GATEWAY_MANIFEST = "/etc/robot-md-gateway/ROBOT.md"


def strip_footer(text: str) -> str:
    """Return the manifest body with any existing ROBOT-MD-SIG footer removed and
    trailing newlines stripped — the canonical pre-image for (re)signing."""
    m = _SIG_RE.search(text)
    core = text[: m.start()] if m else text
    return core.rstrip("\n")


def sign_manifest_footer(
    text: str,
    keypair=None,
    *,
    kid: str | None = None,
    priv_key: ed25519.Ed25519PrivateKey | None = None,
) -> str:
    """Re-sign `text` (a manifest, with or without an existing footer) and return the
    full signed document.

    Two signing identities, ONE core-byte computation (the part the verifier pins):
      * `priv_key` — a raw Ed25519 private key (the registered OPERATOR key); `kid`
        is required and advertised verbatim. Used when RRF resolves an operator kid
        rather than the robot's own pq_kid.
      * `keypair` — a SigningKeypair (the robot keypair); `kid` defaults to its pq_kid.
    """
    core = strip_footer(text)
    if priv_key is not None:
        if kid is None:
            raise ValueError("sign_manifest_footer: kid is required when signing with priv_key")
        sec = priv_key
    else:
        if keypair is None:
            raise ValueError("sign_manifest_footer: pass a keypair or a priv_key")
        if kid is None:
            kid = keypair.pq_kid
        sec = ed25519.Ed25519PrivateKey.from_private_bytes(keypair.ed25519_sec)
    sig = sec.sign(core.encode("utf-8"))
    sig_b64 = base64.b64encode(sig).decode()
    return f"{core}\n<!-- ROBOT-MD-SIG kid={kid} sig={sig_b64} -->\n"


def _operator_key_from_env() -> tuple[ed25519.Ed25519PrivateKey, str] | None:
    """Load (priv_key, kid) from ROBOT_MD_OPERATOR_KEY_PATH + ROBOT_MD_OPERATOR_KID.

    Returns None when either is unset — the caller then uses the robot keypair. RRF
    /v2/keys is keyed by operator kids, so on robots whose registered signer is the
    operator (not the robot), this is the footer-signing identity the gateway resolves.
    """
    key_path = os.environ.get("ROBOT_MD_OPERATOR_KEY_PATH")
    kid = os.environ.get("ROBOT_MD_OPERATOR_KID")
    if not (key_path and kid):
        return None
    from cryptography.hazmat.primitives import serialization

    with open(key_path, "rb") as fh:
        priv = serialization.load_pem_private_key(fh.read(), password=None)
    if not isinstance(priv, ed25519.Ed25519PrivateKey):
        raise RuntimeError(f"ROBOT_MD_OPERATOR_KEY_PATH {key_path!r} is not an Ed25519 private key")
    return priv, kid


def resign_and_deploy(
    manifest_path: str | Path,
    *,
    rrn: str | None = None,
    deploy_path: str | Path | None = None,
    deploy: bool = True,
) -> dict:
    """Re-sign the working manifest after a write, and (optionally) deploy the signed
    copy to the gateway's enforced path so the next gateway op doesn't 403.

    Args:
        manifest_path: the working ROBOT.md that was just mutated.
        rrn: signing identity; defaults to rrn_from_ruri(ROBOT_MD_RURI).
        deploy_path: gateway-enforced manifest path; defaults to
            ROBOT_MD_GATEWAY_MANIFEST_PATH or /etc/robot-md-gateway/ROBOT.md.
        deploy: when False, only re-sign the working copy (the `--no-deploy` flag).

    Returns a dict summary {signed, kid, deployed, deploy_path, backup}.
    Raises RuntimeError with an actionable message if the keypair is missing or the
    deploy target is not writable.
    """
    manifest_path = Path(manifest_path)
    text = manifest_path.read_text()

    op = _operator_key_from_env()
    if op is not None:
        priv, kid_used = op
        signed = sign_manifest_footer(text, priv_key=priv, kid=kid_used)
    else:
        if rrn is None:
            ruri = os.environ.get("ROBOT_MD_RURI")
            if not ruri:
                raise RuntimeError(
                    "resign_and_deploy needs an identity: pass rrn= or set ROBOT_MD_RURI, "
                    "or set ROBOT_MD_OPERATOR_KEY_PATH + ROBOT_MD_OPERATOR_KID."
                )
            rrn = rrn_from_ruri(ruri)
        keypair = load_keypair(rrn)
        if keypair is None:
            raise RuntimeError(
                f"no signing keypair at ~/.robot-md/keys/{rrn}.signing.json — run "
                "`robot-md register` first, or set ROBOT_MD_OPERATOR_KEY_PATH + "
                "ROBOT_MD_OPERATOR_KID to sign with a registered operator key."
            )
        signed = sign_manifest_footer(text, keypair)
        kid_used = keypair.pq_kid

    manifest_path.write_text(signed)

    result = {"signed": True, "kid": kid_used, "deployed": False,
              "deploy_path": None, "backup": None}
    if not deploy:
        return result

    if deploy_path is None:
        deploy_path = os.environ.get("ROBOT_MD_GATEWAY_MANIFEST_PATH", DEFAULT_GATEWAY_MANIFEST)
    deploy_path = Path(deploy_path)

    if deploy_path.resolve() == manifest_path.resolve():
        # Working copy IS the enforced copy — nothing to deploy.
        result.update(deployed=True, deploy_path=str(deploy_path))
        return result

    try:
        if deploy_path.exists():
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = deploy_path.with_name(f"{deploy_path.name}.bak.{stamp}")
            shutil.copy2(deploy_path, backup)
            result["backup"] = str(backup)
        deploy_path.write_text(signed)
    except PermissionError as exc:
        raise RuntimeError(
            f"cannot write the gateway manifest at {deploy_path} ({exc}). "
            "Re-run with privileges to that path, or pass --no-deploy and deploy "
            "the re-signed working manifest manually."
        ) from exc
    result.update(deployed=True, deploy_path=str(deploy_path))
    return result
