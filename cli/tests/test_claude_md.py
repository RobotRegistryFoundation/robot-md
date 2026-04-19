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


# ---------------------------------------------------------------- apply_to_file


def test_apply_writes_new_file(tmp_path):
    from robot_md.claude_md import BEGIN_MARKER, END_MARKER, apply_to_file

    out = tmp_path / "CLAUDE.md"
    action = apply_to_file("# hello\n", out)
    assert action == "wrote"
    assert out.exists()
    text = out.read_text()
    # Sentinels must be present on fresh writes so future runs can update in place.
    assert BEGIN_MARKER in text
    assert END_MARKER in text
    assert "# hello" in text


def test_apply_appends_when_file_exists_without_sentinels(tmp_path):
    from robot_md.claude_md import BEGIN_MARKER, apply_to_file

    out = tmp_path / "CLAUDE.md"
    existing = "# Operator's existing CLAUDE.md\n\nKeep this.\n"
    out.write_text(existing)

    action = apply_to_file("# robot block\n", out)
    assert action == "appended"

    text = out.read_text()
    # Operator's original content must be intact at the top.
    assert text.startswith("# Operator's existing CLAUDE.md")
    assert "Keep this." in text
    # Our block appears below with sentinels.
    assert BEGIN_MARKER in text
    assert "# robot block" in text
    # Appended content must come AFTER the operator's content.
    assert text.index("Keep this.") < text.index(BEGIN_MARKER)


def test_apply_updates_in_place_when_sentinels_present(tmp_path):
    from robot_md.claude_md import apply_to_file

    out = tmp_path / "CLAUDE.md"
    # First run — creates file with sentinels around "# v1".
    apply_to_file("# v1\n", out)
    first = out.read_text()
    assert "# v1" in first

    # Second run — block body changes, sentinels stay, operator content unchanged.
    action = apply_to_file("# v2\n", out)
    assert action == "updated"
    second = out.read_text()
    assert "# v1" not in second
    assert "# v2" in second
    # File didn't grow unboundedly.
    assert second.count("BEGIN robot-md") == 1
    assert second.count("END robot-md") == 1


def test_apply_preserves_operator_content_across_updates(tmp_path):
    from robot_md.claude_md import apply_to_file

    out = tmp_path / "CLAUDE.md"
    # Operator writes their own header first.
    operator_header = "# My project CLAUDE.md\n\n## My conventions\n\n- Use 4-space indent\n"
    out.write_text(operator_header)

    # First robot-md run appends.
    apply_to_file("# robot v1\n", out)
    # Operator adds MORE content BELOW the sentinels afterwards.
    current = out.read_text()
    out.write_text(current + "\n## My follow-up notes\n\nSomething below.\n")

    # Second run updates the sentinel block, leaving everything else intact.
    action = apply_to_file("# robot v2\n", out)
    assert action == "updated"
    final = out.read_text()
    assert "# My project CLAUDE.md" in final
    assert "- Use 4-space indent" in final
    assert "## My follow-up notes" in final
    assert "Something below." in final
    assert "# robot v1" not in final
    assert "# robot v2" in final


def test_apply_force_overwrites_everything(tmp_path):
    from robot_md.claude_md import apply_to_file

    out = tmp_path / "CLAUDE.md"
    out.write_text("# operator content that should be destroyed\n\nlots of stuff.\n")
    action = apply_to_file("# fresh\n", out, force=True)
    assert action == "overwrote"
    text = out.read_text()
    assert "operator content" not in text
    assert "# fresh" in text


def test_apply_is_idempotent_on_bob(tmp_path):
    """Running claude-md twice on a real manifest should not keep growing the file."""
    from robot_md.claude_md import apply_to_file

    manifest = _write(tmp_path, BOB)
    out = tmp_path / "CLAUDE.md"

    rendered = render_claude_md(manifest)
    apply_to_file(rendered, out)
    size_after_first = out.stat().st_size

    apply_to_file(rendered, out)  # second run
    size_after_second = out.stat().st_size

    assert size_after_first == size_after_second
    # Exactly one sentinel pair.
    text = out.read_text()
    assert text.count("BEGIN robot-md") == 1
    assert text.count("END robot-md") == 1


def test_template_lists_all_six_mcp_tools(tmp_path):
    """CLAUDE.md should advertise the full python-MCP tool set."""
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "metadata:\n  robot_name: bob\n"
        "capabilities:\n  - arm.pick\n  - arm.place\n"
        "safety:\n  hitl_gates: []\n"
        "drivers: []\n"
        "---\n\n# bob\nIdentity.\n"
    )

    text = render_claude_md(manifest)
    tools = ("validate", "render", "estop", "estop_clear", "execute_capability", "execute_task")
    for tool in tools:
        assert tool in text, f"expected MCP tool {tool!r} in CLAUDE.md template"


def test_template_motion_row_points_at_execute_capability(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\nmetadata:\n  robot_name: bob\ncapabilities: []\n"
        "safety:\n  hitl_gates: []\ndrivers: []\n---\n\n# bob\n"
    )

    text = render_claude_md(manifest)
    # The "Pick up the X" row should mention execute_capability so Claude
    # knows which tool to call for physical motion.
    assert "execute_capability" in text
