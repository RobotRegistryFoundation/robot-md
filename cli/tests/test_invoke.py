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


# --------------------------------------------------- operator-key signing (Slice 1)


def _write_operator_pem(path, priv=None):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = priv or Ed25519PrivateKey.generate()
    path.write_bytes(
        priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return priv


def test_build_envelope_includes_actuator_name_when_set():
    env = build_envelope(
        ruri="rcan://x/s", tool_name="t", tool_args={}, manifest_path="/p",
        actuator_name="so-arm101",
    )
    assert env["actuator_name"] == "so-arm101"


def test_build_envelope_omits_actuator_name_when_none():
    env = build_envelope(ruri="rcan://x/s", tool_name="t", tool_args={}, manifest_path="/p")
    assert "actuator_name" not in env


def test_sign_envelope_with_ed25519_verifies():
    from cryptography.hazmat.primitives.asymmetric import ed25519

    from robot_md.invoke import sign_envelope_with_ed25519

    priv = ed25519.Ed25519PrivateKey.generate()
    env = build_envelope(
        ruri="rcan://x/s", tool_name="read_state", tool_args={}, manifest_path="/p",
        actuator_name="so-arm101",
    )
    signed = sign_envelope_with_ed25519(env, priv, kid="bob-operator-2026")
    assert signed["envelope_signature"]["kid"] == "bob-operator-2026"
    pre = canonical_json(signed, exclude="envelope_signature")
    priv.public_key().verify(base64.b64decode(signed["envelope_signature"]["sig"]), pre)


def test_load_operator_ed25519_roundtrips(tmp_path):
    from robot_md.invoke import load_operator_ed25519

    priv = _write_operator_pem(tmp_path / "op.pem")
    loaded = load_operator_ed25519(tmp_path / "op.pem")
    assert (
        loaded.public_key().public_bytes_raw()
        == priv.public_key().public_bytes_raw()
    )


def test_load_operator_ed25519_rejects_non_ed25519(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from robot_md.invoke import load_operator_ed25519

    key = ec.generate_private_key(ec.SECP256R1())
    pem = tmp_path / "ec.pem"
    pem.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    with pytest.raises(ValueError, match="Ed25519"):
        load_operator_ed25519(pem)


def test_invoke_command_operator_key_signs_with_operator_and_autofills_ruri(tmp_path, monkeypatch):
    """`robot-md invoke --operator-key --kid` signs with the operator key (not a
    robot keystore), advertises the operator kid, sets actuator_name, and
    auto-constructs ruri when the manifest omits it."""
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "metadata:\n"
        "  robot_name: bob-spec-b-pick-place\n"
        "  manufacturer: bob-spec-b-pick-place\n"
        "  model: so-arm101\n"
        "  rrn: RRN-000000000011\n"
        "manifest_spec_version: '1.0'\n"
        "---\n# robot\n"
    )
    bearers = tmp_path / "bearers.yaml"
    bearers.write_text("- token: tok-actuate\n  tier: actuate\n  caller: cli-test\n")
    op_priv = _write_operator_pem(tmp_path / "operator.pem")
    monkeypatch.setenv("HOME", str(tmp_path))  # no stray robot keystore

    _MockHandler.last_envelope = None
    httpd, _ = _start_mock_gateway()
    try:
        port = httpd.server_address[1]
        res = runner.invoke(
            app,
            [
                "invoke", str(manifest),
                "--tool", "read_state",
                "--scope", "READ",
                "--actuator", "so-arm101",
                "--operator-key", str(tmp_path / "operator.pem"),
                "--kid", "bob-operator-2026",
                "--gateway", f"http://127.0.0.1:{port}",
                "--bearer-from-bearers", str(bearers),
            ],
        )
        assert res.exit_code == 0, res.output
        env = _MockHandler.last_envelope
        assert env is not None
        assert env["actuator_name"] == "so-arm101"
        # ruri auto-filled from manufacturer/model/robot_name
        assert env["ruri"] == (
            "rcan://robotregistryfoundation.org/bob-spec-b-pick-place"
            "/so-arm101/bob-spec-b-pick-place"
        )
        # advertised kid is the operator kid, and the sig verifies against the operator key
        assert env["envelope_signature"]["kid"] == "bob-operator-2026"
        pre = canonical_json(env, exclude="envelope_signature")
        op_priv.public_key().verify(
            base64.b64decode(env["envelope_signature"]["sig"]), pre
        )
    finally:
        httpd.shutdown()


def test_invoke_command_operator_key_requires_kid(tmp_path, monkeypatch):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\nmetadata:\n  robot_name: r\n  manufacturer: m\n  model: x\n"
        "  rrn: RRN-000000000011\nmanifest_spec_version: '1.0'\n---\n# r\n"
    )
    _write_operator_pem(tmp_path / "op.pem")
    monkeypatch.setenv("HOME", str(tmp_path))
    res = runner.invoke(
        app,
        [
            "invoke", str(manifest),
            "--tool", "read_state",
            "--operator-key", str(tmp_path / "op.pem"),
            "--bearer", "tok",
            "--gateway", "http://127.0.0.1:1",
        ],
    )
    assert res.exit_code != 0


# --------------------------------------------------- sign-manifest (Slice 1)

_MANIFEST = (
    "---\nmetadata:\n  robot_name: bob\n  manufacturer: acme\n  model: so-arm101\n"
    "  rrn: RRN-000000000011\nmanifest_spec_version: '1.0'\n---\n# robot\n\nbody.\n"
)


def test_sign_manifest_operator_key_mode(tmp_path):
    from robot_md.manifest_sig import verify_manifest_text

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(_MANIFEST)
    op_priv = _write_operator_pem(tmp_path / "op.pem")
    res = runner.invoke(
        app,
        [
            "sign-manifest", str(manifest),
            "--operator-key", str(tmp_path / "op.pem"),
            "--kid", "bob-operator-2026",
        ],
    )
    assert res.exit_code == 0, res.output
    ok, kid = verify_manifest_text(manifest.read_text(), op_priv.public_key())
    assert ok
    assert kid == "bob-operator-2026"


def test_sign_manifest_self_signs_with_robot_keystore(tmp_path, monkeypatch):
    """No --operator-key: self-sign with the robot's keystore key, advertising
    the robot's pq_kid (the kid `robot-md register` binds as the operator
    authority)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    from robot_md.manifest_sig import verify_manifest_text
    from robot_md.signing import generate_keypair, save_keypair

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(_MANIFEST)
    monkeypatch.setenv("HOME", str(tmp_path))
    kp = generate_keypair()
    save_keypair("RRN-000000000011", kp)

    res = runner.invoke(app, ["sign-manifest", str(manifest)])
    assert res.exit_code == 0, res.output
    # Footer verifies against the robot's Ed25519 key and advertises its pq_kid.
    robot_pub = Ed25519PublicKey.from_public_bytes(kp.ed25519_pub)
    ok, kid = verify_manifest_text(manifest.read_text(), robot_pub)
    assert ok
    assert kid == kp.pq_kid


def test_sign_manifest_self_sign_no_keystore_errors(tmp_path, monkeypatch):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(_MANIFEST)
    monkeypatch.setenv("HOME", str(tmp_path))  # empty keystore
    res = runner.invoke(app, ["sign-manifest", str(manifest)])
    assert res.exit_code != 0


def test_sign_manifest_out_flag_leaves_source_untouched(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(_MANIFEST)
    _write_operator_pem(tmp_path / "op.pem")
    out = tmp_path / "signed.md"
    res = runner.invoke(
        app,
        [
            "sign-manifest", str(manifest),
            "--operator-key", str(tmp_path / "op.pem"),
            "--kid", "k",
            "--out", str(out),
        ],
    )
    assert res.exit_code == 0, res.output
    assert "ROBOT-MD-SIG" in out.read_text()
    assert "ROBOT-MD-SIG" not in manifest.read_text()
