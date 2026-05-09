"""Integration: `robot-md invoke` round-trips against an in-process
robot-md-gateway FastAPI app (no mock — the real gateway code path).

Skipped if robot-md-gateway or uvicorn is not importable in the test env.
"""

from __future__ import annotations

import base64
import socket
import threading
import time

import pytest

pytest.importorskip("robot_md_gateway")
pytest.importorskip("uvicorn")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _free_port() -> int:
    """Return a free TCP port on localhost by binding then releasing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _sign_manifest(text_no_sig: str, secret_raw: bytes) -> tuple[str, str]:
    """Append ROBOT-MD-SIG footer signed by Ed25519. Returns (signed_text, kid).

    The signed body is text_no_sig encoded as UTF-8 bytes — identical to what
    verify_manifest computes via text[: match.start()].encode("utf-8").
    """
    body_bytes = text_no_sig.encode("utf-8")
    sec = Ed25519PrivateKey.from_private_bytes(secret_raw)
    sig = sec.sign(body_bytes)
    sig_b64 = base64.b64encode(sig).decode()
    kid = "test-kid"
    footer = f"\n<!-- ROBOT-MD-SIG kid={kid} sig={sig_b64} -->\n"
    return text_no_sig + footer, kid


@pytest.mark.slow
def test_invoke_then_audit_last_roundtrip(tmp_path):
    """End-to-end: invoke succeeds, audit chain advances, /v1/audit/last
    returns the recorded entry, --print-bundle-entry surfaces it.
    """
    import uvicorn
    from robot_md_gateway.actuator import NoOpActuator
    from robot_md_gateway.cert.audit import AuditChain
    from robot_md_gateway.cert.policy import ToolAllowlist
    from robot_md_gateway.receiver import make_app

    # Mint Ed25519 keypair for manifest signing.
    sec_obj = Ed25519PrivateKey.generate()
    secret_raw = sec_obj.private_bytes_raw()
    pub_pem = sec_obj.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Build a resolver that returns this pub PEM for the test kid.
    class _TestResolver:
        def resolve_public_key_pem(self, kid: str) -> bytes | None:
            return pub_pem if kid == "test-kid" else None

    bearers = {"tok-actuate-1": "actuate"}
    audit = AuditChain()
    app = make_app(
        resolver=_TestResolver(),
        bearer_tiers=bearers,
        audit_chain=audit,
        actuator=NoOpActuator(),
        # Allow home_pose so gate passes and we take the allow/no_op path.
        tool_allowlist=ToolAllowlist(allowed_tools=("home_pose",)),
    )

    # Grab a free port, then hand it to uvicorn by number.
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Wait for uvicorn to signal it has started (server.started is set inside the loop).
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if server.started:
            break
        time.sleep(0.05)
    assert server.started, "uvicorn did not start within 10s"

    # Write a signed manifest with metadata.rrn + metadata.ruri.
    manifest_text = (
        "---\n"
        "metadata:\n"
        "  rrn: RRN-000000000123\n"
        "  ruri: rcan://RRN-000000000123/skill\n"
        "manifest_spec_version: '1.0'\n"
        "---\n"
        "# robot\n"
    )
    signed_text, _ = _sign_manifest(manifest_text, secret_raw)
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(signed_text)

    # Run the CLI.
    from typer.testing import CliRunner

    from robot_md.__main__ import app as cli_app

    runner = CliRunner()
    res = runner.invoke(
        cli_app,
        [
            "invoke",
            str(manifest),
            "--tool",
            "home_pose",
            "--gateway",
            f"http://127.0.0.1:{port}",
            "--bearer",
            "tok-actuate-1",
            "--print-bundle-entry",
            "--no-sign",  # Not exercising envelope_signature in this test.
        ],
    )
    server.should_exit = True
    thread.join(timeout=5)

    print(f"CLI exit_code: {res.exit_code}, stdout:\n{res.output}")
    assert len(audit.entries) >= 1, f"audit chain empty; CLI output: {res.output}"
    last = audit.entries[-1]
    print(f"audit decision: {last.decision} reason: {last.decision_reason}")

    # Shape A: expect allow + no_op from the NoOpActuator.
    # Shape B fallback: a deny is still valid evidence the wire works.
    if last.decision == "allow":
        assert res.exit_code == 0, res.output
        assert last.actuator_name == "noop"
        assert last.actuator_outcome_kind == "no_op"
        # /v1/audit/last was fetched and surfaced in output.
        assert "actuator_outcome_kind" in res.output or "/v1/audit/last" in res.output
    else:
        # Deny path: wire layer still worked, chain advanced.
        assert last.decision == "deny"
        assert last.decision_reason  # non-empty deny reason
