"""robot-md invoke — production RCAN INVOKE envelope sender.

Builds a signed RCAN INVOKE envelope and POSTs it to a robot-md-gateway
`/v1/invoke` endpoint. Operators use this for real dispatches; cookbook
readers use it as the actuation step in beat 6.

No mocks. No demo flags. The signing path uses the operator's
`~/.robot-md/keys/<rrn>.signing.json` keypair (same convention as
`robot-md register`).
"""

from __future__ import annotations

import secrets
import time
import uuid
from typing import Any


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
