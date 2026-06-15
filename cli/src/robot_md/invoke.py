"""robot-md invoke — production RCAN INVOKE envelope sender.

Builds a signed RCAN INVOKE envelope and POSTs it to a robot-md-gateway
`/v1/invoke` endpoint. Operators use this for real dispatches; cookbook
readers use it as the actuation step in beat 6.

No mocks. No demo flags. The signing path uses the operator's
`~/.robot-md/keys/<rrn>.signing.json` keypair (same convention as
`robot-md register`).
"""

from __future__ import annotations

import base64
import json
import secrets
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from rcan.audit_bundle import canonical_json

from robot_md.signing import SigningKeypair


def build_envelope(
    *,
    ruri: str,
    tool_name: str,
    tool_args: dict[str, Any],
    manifest_path: str,
    scope: str = "actuate",
    actuator_name: str | None = None,
) -> dict[str, Any]:
    """Construct a fresh RCAN INVOKE envelope.

    Returned dict shape matches `robot_md_gateway.receiver.InvokeEnvelope`
    plus `nonce` + `timestamp_ms` for replay protection.

    `actuator_name` is required by a gateway configured with multiple actuators
    (it is ignored in single-actuator mode). When set it is included in the
    signed pre-image, so it must be present before `sign_envelope`.
    """
    envelope: dict[str, Any] = {
        "msg_id": str(uuid.uuid4()),
        "type": "rcan/v1/invoke",
        "ruri": ruri,
        "scope": scope,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "manifest_path": manifest_path,
        "nonce": secrets.token_hex(16),
        "timestamp_ms": int(time.time() * 1000),
    }
    if actuator_name is not None:
        envelope["actuator_name"] = actuator_name
    return envelope


def sign_envelope_with_ed25519(
    envelope: dict[str, Any],
    private_key: ed25519.Ed25519PrivateKey,
    *,
    kid: str,
) -> dict[str, Any]:
    """Sign an envelope with a raw Ed25519 private key; return a signed copy.

    Signature is over `canonical_json(signed_envelope, exclude="envelope_signature")`
    matching the gateway's `verify_envelope` pre-image (cert/envelope.py:57).
    This is the operator-authority signing path: the gateway resolves `kid` to a
    registered Ed25519 public key via RRF `/v2/keys/<kid>`.

    Returns: a new dict (input is not mutated) with `envelope_signature` set.
    """
    out = dict(envelope)
    out["envelope_signature"] = {"kid": kid, "sig": ""}  # placeholder for canon
    pre = canonical_json(out, exclude="envelope_signature")
    sig = private_key.sign(pre)
    out["envelope_signature"] = {"kid": kid, "sig": base64.b64encode(sig).decode()}
    return out


def sign_envelope(
    envelope: dict[str, Any],
    keypair: SigningKeypair,
    *,
    kid: str,
) -> dict[str, Any]:
    """Sign an envelope with the Ed25519 half of a robot `SigningKeypair`.

    Thin wrapper over `sign_envelope_with_ed25519`. NOTE: the advertised `kid`
    must resolve at RRF `/v2/keys/<kid>`. A robot's own `pq_kid` generally does
    NOT (the gateway resolves *operator* kids), so production dispatch signs with
    an operator key — see `load_operator_ed25519` / `--operator-key`.
    """
    sec = ed25519.Ed25519PrivateKey.from_private_bytes(keypair.ed25519_sec)
    return sign_envelope_with_ed25519(envelope, sec, kid=kid)


def load_operator_ed25519(pem_path: Path) -> ed25519.Ed25519PrivateKey:
    """Load an operator Ed25519 private key from a PEM file.

    Operator authorities sign with Ed25519 (the half the gateway resolves from
    RRF `/v2/keys/<kid>`). Raises ValueError if the PEM is not an Ed25519 key.
    """
    key = serialization.load_pem_private_key(pem_path.read_bytes(), password=None)
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise ValueError(
            f"{pem_path}: operator key must be an Ed25519 private key "
            f"(got {type(key).__name__})"
        )
    return key


def load_bearer_for_tier(yaml_path: Path, tier: str) -> str:
    """Load the first bearer token matching `tier` from a gateway bearers.yaml.

    Accepts both legacy list-of-entries shape and v0.5.0a1+ dict shape with
    a top-level `bearers:` key (mirrors gateway `BearerStore.from_yaml`).
    """
    if not yaml_path.exists():
        raise FileNotFoundError(f"bearers file not found: {yaml_path}")
    data = yaml.safe_load(yaml_path.read_text())
    if isinstance(data, dict):
        rows = data.get("bearers") or []
    elif isinstance(data, list):
        rows = data
    else:
        raise ValueError(
            f"{yaml_path}: top-level must be a list (legacy) or dict with 'bearers' key"
        )
    for row in rows:
        if row.get("tier") == tier:
            return str(row["token"])
    raise LookupError(f"no bearer entry with tier {tier!r} in {yaml_path}")


def invoke_envelope(
    *,
    envelope: dict[str, Any],
    gateway_url: str,
    bearer: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """POST a (signed or unsigned) envelope to `<gateway_url>/v1/invoke`.

    Returns the parsed JSON response body on 2xx. On 4xx/5xx raises
    RuntimeError with the status code and response body included.
    """
    url = gateway_url.rstrip("/") + "/v1/invoke"
    body = json.dumps(envelope).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"gateway returned {e.code}: {body_text}") from e


def fetch_last_audit_entry(
    *,
    gateway_url: str,
    bearer: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """GET `<gateway_url>/v1/audit/last`, return parsed JSON body."""
    url = gateway_url.rstrip("/") + "/v1/audit/last"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"gateway returned {e.code}: {body_text}") from e
