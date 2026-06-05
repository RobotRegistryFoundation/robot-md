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
import os
import secrets
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import yaml
from cryptography.hazmat.primitives.asymmetric import ed25519
from rcan.audit_bundle import canonical_json

from robot_md.signing import SigningKeypair, load_keypair


def build_envelope(
    *,
    ruri: str,
    tool_name: str,
    tool_args: dict[str, Any],
    manifest_path: str,
    scope: str = "actuate",
) -> dict[str, Any]:
    """Construct a fresh RCAN INVOKE envelope.

    Returned dict shape matches `robot_md_gateway.receiver.InvokeEnvelope`
    plus `nonce` + `timestamp_ms` for replay protection.
    """
    return {
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


def sign_envelope(
    envelope: dict[str, Any],
    keypair: SigningKeypair,
    *,
    kid: str,
) -> dict[str, Any]:
    """Sign an envelope with Ed25519 and return a copy with envelope_signature attached.

    Signature is over `canonical_json(signed_envelope, exclude="envelope_signature")`
    matching the gateway's `verify_envelope` pre-image (cert/envelope.py:57).

    Args:
        envelope: dict from build_envelope (or compatible)
        keypair: operator's signing keypair (from ~/.robot-md/keys/<rrn>.signing.json)
        kid: key id to advertise in the envelope; gateway resolves to a
             registered Ed25519 public key via RRFResolver.

    Returns: a new dict (input is not mutated) with `envelope_signature` set.
    """
    out = dict(envelope)
    out["envelope_signature"] = {"kid": kid, "sig": ""}  # placeholder for canon
    pre = canonical_json(out, exclude="envelope_signature")
    sec = ed25519.Ed25519PrivateKey.from_private_bytes(keypair.ed25519_sec)
    sig = sec.sign(pre)
    out["envelope_signature"] = {"kid": kid, "sig": base64.b64encode(sig).decode()}
    return out


def sign_envelope_with_pem(envelope: dict[str, Any], *, key_path: str, kid: str) -> dict[str, Any]:
    """Sign an envelope with an Ed25519 private-key PEM file, advertising `kid`.

    Same pre-image as `sign_envelope` (`canonical_json(env, exclude="envelope_signature")`,
    cert/envelope.py:57) but loads a raw operator key from disk rather than a
    `SigningKeypair`. Used when `ROBOT_MD_OPERATOR_KEY_PATH`/`ROBOT_MD_OPERATOR_KID`
    select an operator identity that RRF `/v2/keys` actually resolves (the robot's own
    `pq_kid` is not registered there — RRF is keyed by operator kids).
    """
    from cryptography.hazmat.primitives import serialization

    with open(key_path, "rb") as fh:
        priv = serialization.load_pem_private_key(fh.read(), password=None)
    if not isinstance(priv, ed25519.Ed25519PrivateKey):
        raise RuntimeError(
            f"ROBOT_MD_OPERATOR_KEY_PATH {key_path!r} is not an Ed25519 private key"
        )
    out = dict(envelope)
    out["envelope_signature"] = {"kid": kid, "sig": ""}
    pre = canonical_json(out, exclude="envelope_signature")
    out["envelope_signature"] = {
        "kid": kid,
        "sig": base64.b64encode(priv.sign(pre)).decode(),
    }
    return out


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


def rrn_from_ruri(ruri: str) -> str:
    """Extract the RRN-* prefix from an rcan://RRN-.../... URI."""
    if not ruri.startswith("rcan://"):
        raise RuntimeError(f"ROBOT_MD_RURI must start with rcan:// — got {ruri!r}")
    rest = ruri[len("rcan://") :]
    rrn = rest.split("/", 1)[0]
    if not rrn.startswith("RRN-"):
        raise RuntimeError(f"ROBOT_MD_RURI host must be an RRN-* identifier — got {rrn!r}")
    return rrn


def gateway_invoke(
    actuator: str, tool: str, args: dict, *, scope: str | None = None, timeout: float = 10.0
) -> dict:
    """Build, sign, and POST a full RCAN InvokeEnvelope to the gateway.

    The single client used by `trial`, `commission`, `teach`, and
    `calibrate-vision` to route hardware ops through the gateway (audited,
    RCAN-signed, e-stoppable) rather than touching the serial bus directly.

    Required env vars (set once by the operator):

        ROBOT_MD_RURI           e.g. rcan://RRN-000000000002/skill
        ROBOT_MD_SCOPE          default scope when `scope` arg is None
                                ("read" if unset)
        ROBOT_MD_MANIFEST_PATH  absolute path to the signed ROBOT.md the gateway
                                verifies against
        ROBOT_MD_GATEWAY_URL    default http://127.0.0.1:8080
        ROBOT_MD_GATEWAY_BEARER bearer token for the required tier

    Args:
        actuator: multi-actuator routing name (e.g. "so-arm101", "oak-d").
        tool: tool_name the actuator dispatches (move/read_state/perceive/
              commission_probe/raw_tick_move/set_torque/paced_move/...).
        args: tool_args dict.
        scope: RCAN scope override; falls back to ROBOT_MD_SCOPE, then "read".
               Commission/teach/calibrate motion pass scope="actuate" (or the
               COMMISSION scope once the gateway supports it).

    Envelope shape matches `robot_md_gateway.receiver.InvokeEnvelope` plus
    `nonce`/`timestamp_ms`. Signed Ed25519 with the operator keypair at
    `~/.robot-md/keys/<rrn>.signing.json` (the kid is the operator's pq_kid;
    the gateway resolves it via RRFResolver and verifies before dispatch).
    """
    ruri = os.environ.get("ROBOT_MD_RURI")
    if not ruri:
        raise RuntimeError(
            "ROBOT_MD_RURI is required to invoke the gateway. Set it to this "
            "robot's rcan:// RRN registration URI."
        )
    manifest_path = os.environ.get("ROBOT_MD_MANIFEST_PATH")
    if not manifest_path:
        raise RuntimeError(
            "ROBOT_MD_MANIFEST_PATH is required. Set it to the absolute path of "
            "the signed ROBOT.md the gateway should verify against."
        )
    if scope is None:
        scope = os.environ.get("ROBOT_MD_SCOPE", "read")

    rrn = rrn_from_ruri(ruri)

    envelope = build_envelope(
        ruri=ruri,
        tool_name=tool,
        tool_args=args,
        manifest_path=manifest_path,
        scope=scope,
    )
    # Multi-actuator routing field (gateway >= 0.5.0a3). Added pre-signing so
    # it's covered by the signature.
    envelope["actuator_name"] = actuator

    # Signing identity. RRF `/v2/keys` is keyed by OPERATOR kids, not the robot's own
    # `pq_kid` — so deployments where the operator (not the robot) is the registered
    # signer set ROBOT_MD_OPERATOR_KEY_PATH + ROBOT_MD_OPERATOR_KID to sign with the
    # operator's Ed25519 key. Absent both, fall back to the robot keypair convention
    # (~/.robot-md/keys/<rrn>.signing.json, kid = pq_kid).
    op_key_path = os.environ.get("ROBOT_MD_OPERATOR_KEY_PATH")
    op_kid = os.environ.get("ROBOT_MD_OPERATOR_KID")
    # Fail loud on a half-set operator identity — silently falling back to the robot pq_kid
    # (which RRF doesn't resolve) would surface only as a cryptic downstream 403.
    if bool(op_key_path) != bool(op_kid):
        raise RuntimeError(
            "partial operator-key config: set BOTH ROBOT_MD_OPERATOR_KEY_PATH and "
            "ROBOT_MD_OPERATOR_KID, or neither."
        )
    if op_key_path and op_kid:
        envelope = sign_envelope_with_pem(envelope, key_path=op_key_path, kid=op_kid)
    else:
        keypair = load_keypair(rrn)
        if keypair is None:
            raise RuntimeError(
                f"no signing keypair at ~/.robot-md/keys/{rrn}.signing.json — run "
                "`robot-md register` first, or set ROBOT_MD_OPERATOR_KEY_PATH + "
                "ROBOT_MD_OPERATOR_KID to sign with a registered operator key."
            )
        envelope = sign_envelope(envelope, keypair, kid=keypair.pq_kid)

    gateway_url = os.environ.get("ROBOT_MD_GATEWAY_URL", "http://127.0.0.1:8080")
    bearer = os.environ.get("ROBOT_MD_GATEWAY_BEARER", "")
    return invoke_envelope(
        envelope=envelope, gateway_url=gateway_url, bearer=bearer, timeout=timeout
    )


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
