"""Tests for robot-md claude-md — CLAUDE.md generator."""

from __future__ import annotations

from pathlib import Path

from robot_md.claude_md import render_claude_md

BOB = """---
rcan_version: "3.0"
metadata:
  robot_name: bob
  manufacturer: acme
  model: so-arm101
  version: "1.0"
  device_id: bob-001
  rrn: RRN-000000000003
physics:
  type: arm
  dof: 6
drivers:
  - id: arm
    protocol: feetech
    port: /dev/ttyACM0
capabilities:
  - arm.pick
safety:
  estop:
    software: true
    response_ms: 100
  hitl_gates:
    - scope: destructive
      require_auth: true
    - scope: system
      require_auth: true
---

# bob

## Identity
Test arm.

## What bob Can Do
Pick.

## Safety Gates
E-stop at 100ms.
"""


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "ROBOT.md"
    p.write_text(content)
    return p


def test_render_substitutes_robot_name(tmp_path):
    p = _write(tmp_path, BOB)
    text = render_claude_md(p)
    assert "# CLAUDE.md — bob" in text
    assert "robot-md://bob/frontmatter" in text
    # No unsubstituted substitution targets remain. (The meta-text
    # "`{{...}}` or `TODO`" in the intro is literal, so we check for
    # our specific placeholder names instead.)
    for placeholder in (
        "{{ROBOT_NAME}}",
        "{{RRN}}",
        "{{DRIVER}}",
        "{{HITL_GATES_LIST}}",
        "{{HOSTNAME}}",
        "{{DATE}}",
        "{{PUBLIC_RESOLVER_LINE}}",
    ):
        assert placeholder not in text, f"{placeholder} not substituted"


def test_render_includes_rrn_and_resolver(tmp_path):
    p = _write(tmp_path, BOB)
    text = render_claude_md(p)
    assert "RRN-000000000003" in text
    assert "https://rcan.dev/r/RRN-000000000003" in text


def test_render_lists_declared_hitl_gates(tmp_path):
    p = _write(tmp_path, BOB)
    text = render_claude_md(p)
    assert "`destructive`" in text
    assert "`system`" in text
    assert "requires explicit authorization" in text


def test_render_flags_missing_gates(tmp_path):
    content = BOB.replace(
        """  hitl_gates:
    - scope: destructive
      require_auth: true
    - scope: system
      require_auth: true
""",
        "",
    )
    p = _write(tmp_path, content)
    text = render_claude_md(p)
    assert "No HITL gates declared" in text


def test_render_unregistered_robot_omits_resolver(tmp_path):
    content = BOB.replace("  rrn: RRN-000000000003\n", "")
    p = _write(tmp_path, content)
    text = render_claude_md(p)
    assert "(unregistered)" in text
    assert "resolves at" not in text


def test_render_summarizes_primary_driver(tmp_path):
    p = _write(tmp_path, BOB)
    text = render_claude_md(p)
    assert "feetech" in text
    assert "/dev/ttyACM0" in text
