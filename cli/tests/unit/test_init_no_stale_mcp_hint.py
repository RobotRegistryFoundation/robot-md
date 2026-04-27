"""init's _print_tally must not emit the stale npm-based claude mcp add hint.

After SP1 R1 (Phase 3) deprecated phase_install_mcp to a no-op, the old
'register MCP manually' fallback in _print_tally fires on every default
init because install_mcp's status is now always 'skipped' (never 'ok').
The fallback printed the old npm-based command:

  claude mcp add robot-md-<name> -- robot-md-mcp "<path>"

That contradicts the new deprecation message and confuses operators.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from robot_md.init import _print_tally
from robot_md.init_phases import PhaseResult


def _stub_skipped_install_mcp_result() -> PhaseResult:
    """The PhaseResult shape phase_install_mcp returns post-Phase 3."""
    return PhaseResult(
        phase="install_mcp",
        status="skipped",
        message="MCP wiring is handled by the robot-md plugin's .mcp.json. ...",
        detail={"deprecated_in": "1.2.0", "reason": "plugin_handles_mcp"},
    )


def _make_fake_parsed(robot_name: str) -> MagicMock:
    """Return a fake ParsedRobotMd-like object with a known robot_name."""
    fake = MagicMock()
    fake.frontmatter = {"metadata": {"robot_name": robot_name}}
    return fake


def test_print_tally_does_not_emit_stale_npm_hint(capsys, tmp_path: Path):
    """_print_tally with a skipped install_mcp result must not print the
    old `claude mcp add robot-md-<name> -- robot-md-mcp` command."""
    results = [_stub_skipped_install_mcp_result()]
    # _print_tally does `from robot_md.parser import parse_file` inside a
    # try/except; patching at the module level makes the local import pick
    # up the mock.
    with patch("robot_md.parser.parse_file", return_value=_make_fake_parsed("bob")):
        _print_tally(
            results=results,
            out_path=tmp_path / "ROBOT.md",
        )
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    # "robot-md-mcp" is the old npm-binary name used only in the stale hint;
    # it must never appear in output regardless of the install_mcp status.
    assert "robot-md-mcp" not in combined, (
        "init must not reference the stale robot-md-mcp npm binary. "
        f"Output:\n{combined}"
    )
    assert "To register the MCP server manually" not in combined, (
        "init must not emit the stale 'register MCP manually' prompt. "
        f"Output:\n{combined}"
    )


def test_print_tally_does_not_emit_stale_hint_when_install_mcp_absent(
    capsys, tmp_path: Path
):
    """If install_mcp wasn't run at all (Phase 4 will drop it from
    default_flow), _print_tally must still not emit the stale hint."""
    results = []  # No install_mcp at all
    with patch("robot_md.parser.parse_file", return_value=_make_fake_parsed("bob")):
        _print_tally(
            results=results,
            out_path=tmp_path / "ROBOT.md",
        )
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "robot-md-mcp" not in combined, (
        "init must not reference the stale robot-md-mcp npm binary. "
        f"Output:\n{combined}"
    )
    assert "To register the MCP server manually" not in combined, (
        "init must not emit the stale 'register MCP manually' prompt. "
        f"Output:\n{combined}"
    )
