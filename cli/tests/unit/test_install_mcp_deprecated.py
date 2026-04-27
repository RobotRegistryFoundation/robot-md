"""install_mcp phase is deprecated to a no-op per SP1.

Per the simplified one-server design (Revision R1), the plugin's
.mcp.json wires the Python `robot-md mcp` server. init no longer needs
`claude mcp add`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from robot_md.init_phases.install_mcp import phase_install_mcp


@pytest.fixture
def stub_manifest(tmp_path: Path) -> Path:
    """Minimal valid ROBOT.md so phase doesn't fail on parse."""
    p = tmp_path / "ROBOT.md"
    p.write_text(
        "---\n"
        "metadata:\n"
        "  robot_name: stub\n"
        "physics:\n"
        "  type: arm\n"
        "  dof: 6\n"
        "drivers: []\n"
        "capabilities: []\n"
        "---\n"
        "# stub\n"
    )
    return p


def test_phase_install_mcp_returns_skipped(stub_manifest: Path):
    """The deprecated phase must return status=skipped, never ok or failed."""
    result = phase_install_mcp(stub_manifest)
    assert result.status == "skipped"
    assert result.phase == "install_mcp"


def test_phase_install_mcp_does_not_shell_out(stub_manifest: Path):
    """The deprecated phase must NOT call subprocess (no `claude mcp add`)."""
    with patch.object(subprocess, "run") as mock_run:
        phase_install_mcp(stub_manifest)
    assert mock_run.call_count == 0, (
        f"install_mcp shelled out {mock_run.call_count} times — "
        "should be 0 in the deprecated implementation"
    )


def test_phase_install_mcp_message_explains_plugin_handles_wiring(
    stub_manifest: Path,
):
    """Message should tell operators the plugin handles MCP wiring now."""
    result = phase_install_mcp(stub_manifest)
    assert "plugin" in result.message.lower()
    assert "/mcp" in result.message or "Reconnect" in result.message


def test_phase_install_mcp_signature_unchanged_for_backward_compat(
    stub_manifest: Path,
):
    """Old callers passing command/scope kwargs must not break."""
    # Was: phase_install_mcp(path, command="robot-md-mcp", scope="local")
    result = phase_install_mcp(stub_manifest, command="robot-md-mcp", scope="local")
    assert result.status == "skipped"
