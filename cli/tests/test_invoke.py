"""Tests for robot-md invoke — production RCAN INVOKE envelope sender."""

from __future__ import annotations

import uuid

from robot_md.invoke import build_envelope


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
