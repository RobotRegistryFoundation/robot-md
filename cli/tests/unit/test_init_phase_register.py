"""Unit tests for phase_register."""
from __future__ import annotations

from unittest.mock import patch


def test_ok_when_cli_register_returns_zero(tmp_path):
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n  rrn: RRN-ABC123456789\n---\n")

    with patch("robot_md.init_phases.register.cli_register", return_value=0) as run:
        result = phase_register(manifest, contact_email="me@acme.com")

    assert result.status == "ok"
    assert result.detail and result.detail.get("rrn") == "RRN-ABC123456789"
    run.assert_called_once()
    assert run.call_args.kwargs.get("contact_email") == "me@acme.com"


def test_failed_when_cli_register_returns_nonzero(tmp_path):
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n---\n")

    with patch("robot_md.init_phases.register.cli_register", return_value=1):
        result = phase_register(manifest, contact_email="me@acme.com")

    assert result.status == "failed"
    assert result.detail and result.detail.get("exit_code") == 1


def test_passes_through_optional_overrides(tmp_path):
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n---\n")

    with patch("robot_md.init_phases.register.cli_register", return_value=0) as run:
        phase_register(
            manifest,
            contact_email="me@acme.com",
            manufacturer="acme",
            model="so-arm101",
            version="1.0",
            device_id="bob",
        )

    kw = run.call_args.kwargs
    assert kw["manufacturer"] == "acme"
    assert kw["model"] == "so-arm101"
    assert kw["version"] == "1.0"
    assert kw["device_id"] == "bob"


def test_ok_with_missing_rrn_returns_fallback_message(tmp_path):
    """cli_register succeeded but the RRN is absent from the manifest afterward.

    Exercises the `registered (RRN not yet written)` fallback branch.
    """
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n---\n")

    with patch("robot_md.init_phases.register.cli_register", return_value=0):
        result = phase_register(manifest)

    assert result.status == "ok"
    assert result.message == "registered (RRN not yet written)"
    assert result.detail == {"rrn": "", "exit_code": 0}


def test_ok_when_manifest_reparse_fails(tmp_path):
    """If parse_file raises after a successful mint, fall back to empty rrn
    rather than crashing the phase — the registration itself still succeeded.
    """
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n---\n")

    with (
        patch("robot_md.init_phases.register.cli_register", return_value=0),
        patch("robot_md.init_phases.register.parse_file", side_effect=RuntimeError("boom")),
    ):
        result = phase_register(manifest)

    assert result.status == "ok"
    assert result.detail == {"rrn": "", "exit_code": 0}
