"""Tests for robot-md invoke — production RCAN INVOKE envelope sender."""

from __future__ import annotations

import base64
import copy
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from rcan.audit_bundle import canonical_json

from robot_md.invoke import build_envelope, sign_envelope
from robot_md.signing import generate_keypair


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
    for k in ("msg_id", "type", "ruri", "scope", "tool_name", "tool_args",
              "manifest_path", "nonce", "timestamp_ms"):
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
        ruri="rcan://x/s", tool_name="t", tool_args={}, manifest_path="/p",
    )
    snapshot = copy.deepcopy(env)
    sign_envelope(env, kp, kid="k")
    assert env == snapshot
