"""Package-import smoke test for init_phases."""

from __future__ import annotations

from unittest.mock import patch


def test_phase_result_exports():
    from robot_md.init_phases import PhaseResult

    r = PhaseResult(phase="x", status="ok", message="ok", detail=None)
    assert r.phase == "x"
    assert r.status == "ok"
    assert r.message == "ok"
    assert r.detail is None


def test_phase_result_accepts_skipped_and_failed():
    from robot_md.init_phases import PhaseResult

    assert PhaseResult(phase="x", status="skipped", message="m", detail=None).status == "skipped"
    assert PhaseResult(phase="x", status="failed", message="m", detail={"e": 1}).detail == {"e": 1}


def test_phase_install_mcp_derives_server_name_from_robot_name(tmp_path):
    from robot_md.init_phases import PhaseResult, phase_install_mcp

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n---\n\n# bob\n")

    fake_result = PhaseResult(
        phase="install_mcp",
        status="ok",
        message="registered 'robot-md-bob'",
        detail={"server_name": "robot-md-bob", "scope": "local", "already_registered": False},
    )
    with patch("robot_md.init_phases.install_mcp.add", return_value=fake_result) as add:
        result = phase_install_mcp(manifest)

    assert result.status == "ok"
    assert add.call_args.args[0] == "robot-md-bob"
    assert add.call_args.args[1] == manifest


def test_phase_install_mcp_returns_failed_when_manifest_missing_name(tmp_path):
    from robot_md.init_phases import phase_install_mcp

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata: {}\n---\n\n# robot\n")

    result = phase_install_mcp(manifest)
    assert result.status == "failed"
    assert "robot_name" in result.message.lower()
