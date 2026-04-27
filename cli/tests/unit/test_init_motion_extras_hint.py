"""init prints the pip install hint when manifest declares motion caps.

Per SP1 §2.2 + revision R3, init emits a closing line pointing at
`pip install 'robot-md[hardware]'` whenever the manifest declares
arm.*/nav.*/gripper.*/perceive.* capabilities.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_md.init import _emit_motion_extras_hint


def _run_hint(capabilities: list[str], capsys) -> str:
    """Helper: call the hint emitter and return captured stderr."""
    _emit_motion_extras_hint(capabilities)
    captured = capsys.readouterr()
    return captured.err


def test_hint_emitted_for_arm_pick(capsys):
    out = _run_hint(["arm.pick", "arm.place"], capsys)
    assert "pip install" in out
    assert "robot-md[hardware]" in out


def test_hint_emitted_for_nav(capsys):
    out = _run_hint(["nav.go_to"], capsys)
    assert "pip install" in out


def test_hint_emitted_for_perceive(capsys):
    out = _run_hint(["perceive.rgb"], capsys)
    assert "pip install" in out


def test_hint_emitted_for_gripper(capsys):
    out = _run_hint(["gripper.open"], capsys)
    assert "pip install" in out


def test_hint_suppressed_for_empty_capabilities(capsys):
    out = _run_hint([], capsys)
    assert out == "" or "pip install" not in out


def test_hint_suppressed_for_nonmotion_capabilities(capsys):
    """Capabilities like compute.* don't need motion runtime."""
    out = _run_hint(["compute.train", "logging.publish"], capsys)
    assert "pip install" not in out


def test_hint_mentions_mcp_reconnect(capsys):
    """Operators need to know about the /mcp Reconnect step."""
    out = _run_hint(["arm.pick"], capsys)
    assert "/mcp" in out or "Reconnect" in out


def test_hint_uses_hardware_extra_not_old_npm():
    """Sanity: the hint must not reference the deprecated npm-based command."""
    import sys, io
    buf = io.StringIO()
    _orig = sys.stderr
    sys.stderr = buf
    try:
        _emit_motion_extras_hint(["arm.pick"])
    finally:
        sys.stderr = _orig
    out = buf.getvalue()
    assert "robot-md-mcp" not in out
    assert "claude mcp add" not in out
