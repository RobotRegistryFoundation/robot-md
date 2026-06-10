"""Tests for robot-md invoke — production RCAN INVOKE envelope sender."""

from __future__ import annotations

import base64
import copy
import http.server
import json as _json
import socketserver
import threading
import uuid
from typing import Any, ClassVar

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from rcan.audit_bundle import canonical_json
from typer.testing import CliRunner

from robot_md.__main__ import app
from robot_md.invoke import (
    build_envelope,
    fetch_last_audit_entry,
    invoke_envelope,
    load_bearer_for_tier,
    sign_envelope,
)
from robot_md.signing import generate_keypair

runner = CliRunner()


def test_build_envelope_minimal():
    env = build_envelope(
        ruri="rcan://RRN-000000000123/skill",
        tool_name="home_pose",
        tool_args={"speed": 0.3},
        manifest_path="/tmp/ROBOT.md",
        scope="actuate",
    )
    assert env["type"] == "rcan/v1/invoke"
    assert env["ruri"] == "rcan://RRN-000000000123/skill"
    assert env["scope"] == "actuate"
    assert env["tool_name"] == "home_pose"
    assert env["tool_args"] == {"speed": 0.3}
    assert env["manifest_path"] == "/tmp/ROBOT.md"
    # msg_id must be a uuid4
    uuid.UUID(env["msg_id"], version=4)
    # nonce is opaque hex; non-empty
    assert isinstance(env["nonce"], str) and len(env["nonce"]) >= 16
    # timestamp_ms is positive integer (epoch ms)
    assert isinstance(env["timestamp_ms"], int) and env["timestamp_ms"] > 0


def test_build_envelope_default_scope_is_actuate():
    env = build_envelope(
        ruri="rcan://RRN-000000000123/skill",
        tool_name="home_pose",
        tool_args={},
        manifest_path="/tmp/ROBOT.md",
    )
    assert env["scope"] == "actuate"


def test_build_envelope_unique_msg_ids():
    a = build_envelope(ruri="rcan://x/s", tool_name="t", tool_args={}, manifest_path="/p")
    b = build_envelope(ruri="rcan://x/s", tool_name="t", tool_args={}, manifest_path="/p")
    assert a["msg_id"] != b["msg_id"]


def test_sign_envelope_attaches_envelope_signature():
    kp = generate_keypair()
    env = build_envelope(
        ruri="rcan://RRN-000000000123/skill",
        tool_name="home_pose",
        tool_args={},
        manifest_path="/tmp/ROBOT.md",
    )
    signed = sign_envelope(env, kp, kid="op-2026-key-1")
    assert "envelope_signature" in signed
    assert signed["envelope_signature"]["kid"] == "op-2026-key-1"
    assert signed["envelope_signature"]["sig"]
    # All original fields preserved
    for k in (
        "msg_id",
        "type",
        "ruri",
        "scope",
        "tool_name",
        "tool_args",
        "manifest_path",
        "nonce",
        "timestamp_ms",
    ):
        assert signed[k] == env[k]


def test_sign_envelope_signature_verifies_with_ed25519_pub():
    kp = generate_keypair()
    env = build_envelope(
        ruri="rcan://RRN-000000000123/skill",
        tool_name="home_pose",
        tool_args={},
        manifest_path="/tmp/ROBOT.md",
    )
    signed = sign_envelope(env, kp, kid="op-2026-key-1")
    pub = Ed25519PublicKey.from_public_bytes(kp.ed25519_pub)
    sig = base64.b64decode(signed["envelope_signature"]["sig"])
    pre = canonical_json(signed, exclude="envelope_signature")
    pub.verify(sig, pre)  # raises InvalidSignature on mismatch


def test_sign_envelope_does_not_mutate_input():
    kp = generate_keypair()
    env = build_envelope(
        ruri="rcan://x/s",
        tool_name="t",
        tool_args={},
        manifest_path="/p",
    )
    snapshot = copy.deepcopy(env)
    sign_envelope(env, kp, kid="k")
    assert env == snapshot


def test_load_bearer_for_tier_actuate_legacy_list_shape(tmp_path):
    yaml_path = tmp_path / "bearers.yaml"
    yaml_path.write_text(
        "- token: tok-a\n"
        "  tier: read\n"
        "  caller: claude-read\n"
        "- token: tok-b\n"
        "  tier: actuate\n"
        "  caller: claude-actuate\n"
    )
    assert load_bearer_for_tier(yaml_path, "actuate") == "tok-b"


def test_load_bearer_for_tier_v0_5_dict_shape(tmp_path):
    yaml_path = tmp_path / "bearers.yaml"
    yaml_path.write_text(
        "bearers:\n"
        "  - token: tok-a\n"
        "    tier: read\n"
        "    caller: claude-read\n"
        "  - token: tok-b\n"
        "    tier: actuate\n"
        "    caller: claude-actuate\n"
        "actuator:\n"
        "  name: noop\n"
    )
    assert load_bearer_for_tier(yaml_path, "actuate") == "tok-b"


def test_load_bearer_for_tier_no_match_raises(tmp_path):
    yaml_path = tmp_path / "bearers.yaml"
    yaml_path.write_text("- token: tok-a\n  tier: read\n  caller: claude-read\n")
    with pytest.raises(LookupError, match="no bearer entry with tier 'actuate'"):
        load_bearer_for_tier(yaml_path, "actuate")


def test_load_bearer_for_tier_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_bearer_for_tier(tmp_path / "nope.yaml", "actuate")


class _MockHandler(http.server.BaseHTTPRequestHandler):
    """Simple mock gateway. Class attributes capture state across requests."""

    last_envelope: ClassVar[dict[str, Any] | None] = None
    last_authorization: ClassVar[str | None] = None
    invoke_response: ClassVar[dict[str, Any]] = {
        "ok": True,
        "manifest_kid": "test-kid",
        "scope": "actuate",
        "tool_name": "home_pose",
        "actuator_name": "noop",
        "outcome_kind": "no_op",
    }
    audit_last_response: ClassVar[dict[str, Any]] = {
        "msg_id": "fixed-msg",
        "decision": "allow",
        "actuator_name": "noop",
        "actuator_outcome_kind": "no_op",
    }

    def log_message(self, *_a, **_kw):  # silence test output
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        type(self).last_envelope = _json.loads(body)
        type(self).last_authorization = self.headers.get("Authorization")
        payload = _json.dumps(type(self).invoke_response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        type(self).last_authorization = self.headers.get("Authorization")
        payload = _json.dumps(type(self).audit_last_response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start_mock_gateway():
    httpd = socketserver.TCPServer(("127.0.0.1", 0), _MockHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def test_invoke_envelope_posts_to_gateway_with_bearer():
    _MockHandler.last_envelope = None
    _MockHandler.last_authorization = None
    httpd, _ = _start_mock_gateway()
    try:
        port = httpd.server_address[1]
        env = build_envelope(
            ruri="rcan://RRN-000000000123/skill",
            tool_name="home_pose",
            tool_args={"speed": 0.3},
            manifest_path="/tmp/ROBOT.md",
        )
        result = invoke_envelope(
            envelope=env,
            gateway_url=f"http://127.0.0.1:{port}",
            bearer="tok-actuate-1",
        )
        assert result["ok"] is True
        assert result["actuator_name"] == "noop"
        assert _MockHandler.last_authorization == "Bearer tok-actuate-1"
        assert _MockHandler.last_envelope["msg_id"] == env["msg_id"]
    finally:
        httpd.shutdown()


def test_fetch_last_audit_entry_returns_dict():
    _MockHandler.last_authorization = None
    httpd, _ = _start_mock_gateway()
    try:
        port = httpd.server_address[1]
        entry = fetch_last_audit_entry(
            gateway_url=f"http://127.0.0.1:{port}",
            bearer="tok-actuate-1",
        )
        assert entry["msg_id"] == "fixed-msg"
        assert entry["actuator_outcome_kind"] == "no_op"
        assert _MockHandler.last_authorization == "Bearer tok-actuate-1"
    finally:
        httpd.shutdown()


def test_invoke_envelope_raises_on_4xx():
    class _Reject(_MockHandler):
        def do_POST(self):
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            payload = b'{"detail":"unknown bearer"}'
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    httpd = socketserver.TCPServer(("127.0.0.1", 0), _Reject)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        env = build_envelope(ruri="rcan://x/s", tool_name="t", tool_args={}, manifest_path="/p")
        with pytest.raises(RuntimeError, match="403"):
            invoke_envelope(
                envelope=env,
                gateway_url=f"http://127.0.0.1:{port}",
                bearer="bad-token",
            )
    finally:
        httpd.shutdown()


def test_gateway_invoke_signs_operator_kid_when_env_set(tmp_path, monkeypatch):
    """On Bob the RRF registers OPERATOR kids, not the robot's pq_kid. gateway_invoke
    must sign with a configured operator key/kid (ROBOT_MD_OPERATOR_KEY_PATH/KID) and
    NOT require a ~/.robot-md/keys/<rrn>.signing.json robot keypair at all."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    key_path = tmp_path / "operator.priv.pem"
    key_path.write_bytes(pem)

    _MockHandler.last_envelope = None
    httpd, _ = _start_mock_gateway()
    try:
        port = httpd.server_address[1]
        # HOME points at an empty dir → there is NO robot keypair; the operator path
        # must not fall back to load_keypair().
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("ROBOT_MD_RURI", "rcan://RRN-000000000002/skill")
        monkeypatch.setenv("ROBOT_MD_MANIFEST_PATH", "/etc/robot-md-gateway/ROBOT.md")
        monkeypatch.setenv("ROBOT_MD_GATEWAY_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setenv("ROBOT_MD_GATEWAY_BEARER", "tok-commission")
        monkeypatch.setenv("ROBOT_MD_OPERATOR_KEY_PATH", str(key_path))
        monkeypatch.setenv("ROBOT_MD_OPERATOR_KID", "bob-operator-2026")

        from robot_md.invoke import gateway_invoke

        gateway_invoke("so-arm101", "commission_probe", {"joint_id": "gripper"}, scope="COMMISSION")

        env = _MockHandler.last_envelope
        assert env is not None
        assert env["envelope_signature"]["kid"] == "bob-operator-2026"
        assert env["actuator_name"] == "so-arm101"
        assert env["scope"] == "COMMISSION"
        # Signature verifies against the operator pubkey over the exclude pre-image.
        pub = priv.public_key()
        sig = base64.b64decode(env["envelope_signature"]["sig"])
        pre = canonical_json(env, exclude="envelope_signature")
        pub.verify(sig, pre)  # raises InvalidSignature on mismatch
    finally:
        httpd.shutdown()


def test_gateway_invoke_falls_back_to_robot_keypair_when_operator_env_unset(tmp_path, monkeypatch):
    """Without the operator env, the existing behavior (sign with the robot keypair's
    pq_kid from ~/.robot-md/keys/<rrn>.signing.json) is preserved."""
    from robot_md.signing import generate_keypair, save_keypair

    _MockHandler.last_envelope = None
    httpd, _ = _start_mock_gateway()
    try:
        port = httpd.server_address[1]
        monkeypatch.setenv("HOME", str(tmp_path))
        kp = generate_keypair()
        save_keypair("RRN-000000000002", kp)
        monkeypatch.setenv("ROBOT_MD_RURI", "rcan://RRN-000000000002/skill")
        monkeypatch.setenv("ROBOT_MD_MANIFEST_PATH", "/x/ROBOT.md")
        monkeypatch.setenv("ROBOT_MD_GATEWAY_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setenv("ROBOT_MD_GATEWAY_BEARER", "tok")
        monkeypatch.delenv("ROBOT_MD_OPERATOR_KEY_PATH", raising=False)
        monkeypatch.delenv("ROBOT_MD_OPERATOR_KID", raising=False)

        from robot_md.invoke import gateway_invoke

        gateway_invoke("so-arm101", "read_state", {}, scope="read")

        env = _MockHandler.last_envelope
        assert env is not None
        assert env["envelope_signature"]["kid"] == kp.pq_kid
    finally:
        httpd.shutdown()


def test_gateway_invoke_partial_operator_env_raises(monkeypatch):
    """Setting exactly one of the operator-key env vars must fail loud, not silently fall
    back to the robot pq_kid (which RRF doesn't resolve -> cryptic downstream 403)."""
    monkeypatch.setenv("ROBOT_MD_RURI", "rcan://RRN-000000000002/skill")
    monkeypatch.setenv("ROBOT_MD_MANIFEST_PATH", "/x/ROBOT.md")
    monkeypatch.setenv("ROBOT_MD_OPERATOR_KEY_PATH", "/some/operator.pem")
    monkeypatch.delenv("ROBOT_MD_OPERATOR_KID", raising=False)
    from robot_md.invoke import gateway_invoke

    with pytest.raises(RuntimeError, match="partial operator-key config"):
        gateway_invoke("so-arm101", "read_state", {}, scope="read")


def test_invoke_command_help_shows_required_args():
    res = runner.invoke(
        app,
        ["invoke", "--help"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code == 0
    out = res.stdout
    assert "--tool" in out
    assert "--gateway" in out
    assert "--bearer" in out or "--bearer-from-bearers" in out


def test_invoke_command_emits_signed_envelope_against_mock(tmp_path, monkeypatch):
    """End-to-end: write a manifest + a bearers.yaml + a signing key, run
    `robot-md invoke`, expect 0 exit code and the mock gateway to see the
    signed envelope.
    """
    # Write a minimal valid manifest.
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "metadata:\n"
        "  rrn: RRN-000000000123\n"
        "  ruri: rcan://RRN-000000000123/skill\n"
        "manifest_spec_version: '1.0'\n"
        "---\n"
        "# robot\n"
    )
    # Bearers.yaml (legacy list shape — exercised by load_bearer_for_tier).
    bearers = tmp_path / "bearers.yaml"
    bearers.write_text("- token: tok-actuate\n  tier: actuate\n  caller: cli-test\n")
    # Stash a signing keypair where signing.load_keypair finds it.
    monkeypatch.setenv("HOME", str(tmp_path))
    from robot_md.signing import generate_keypair, save_keypair

    save_keypair("RRN-000000000123", generate_keypair())

    # Spin up the mock gateway.
    _MockHandler.last_envelope = None
    httpd, _ = _start_mock_gateway()
    try:
        port = httpd.server_address[1]
        res = runner.invoke(
            app,
            [
                "invoke",
                str(manifest),
                "--tool",
                "home_pose",
                "--args",
                '{"speed": 0.3}',
                "--gateway",
                f"http://127.0.0.1:{port}",
                "--bearer-from-bearers",
                str(bearers),
            ],
        )
        assert res.exit_code == 0, res.output
        assert _MockHandler.last_envelope is not None
        assert _MockHandler.last_envelope["tool_name"] == "home_pose"
        assert _MockHandler.last_envelope["tool_args"] == {"speed": 0.3}
        # Signed by default.
        assert "envelope_signature" in _MockHandler.last_envelope
    finally:
        httpd.shutdown()
