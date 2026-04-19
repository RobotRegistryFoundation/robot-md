"""Unit tests for phase_register."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from robot_md.validate import VALID


def _mock_valid():
    """Return a MagicMock that mimics a VALID validate_parsed result."""
    m = MagicMock()
    m.code = VALID
    m.errors = []
    m.summary = "ok"
    return m


def test_ok_when_cli_register_returns_zero(tmp_path):
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n  rrn: RRN-ABC123456789\n---\n")

    with (
        patch("robot_md.init_phases.register.validate_parsed", return_value=_mock_valid()),
        patch("robot_md.init_phases.register.cli_register", return_value=0) as run,
    ):
        result = phase_register(manifest, contact_email="me@acme.com")

    assert result.status == "ok"
    assert result.detail and result.detail.get("rrn") == "RRN-ABC123456789"
    run.assert_called_once()
    assert run.call_args.kwargs.get("contact_email") == "me@acme.com"


def test_failed_when_cli_register_returns_nonzero(tmp_path):
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n---\n")

    with (
        patch("robot_md.init_phases.register.validate_parsed", return_value=_mock_valid()),
        patch("robot_md.init_phases.register.cli_register", return_value=1),
    ):
        result = phase_register(manifest, contact_email="me@acme.com")

    assert result.status == "failed"
    assert result.detail and result.detail.get("exit_code") == 1


def test_passes_through_optional_overrides(tmp_path):
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n---\n")

    with (
        patch("robot_md.init_phases.register.validate_parsed", return_value=_mock_valid()),
        patch("robot_md.init_phases.register.cli_register", return_value=0) as run,
    ):
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

    with (
        patch("robot_md.init_phases.register.validate_parsed", return_value=_mock_valid()),
        patch("robot_md.init_phases.register.cli_register", return_value=0),
    ):
        result = phase_register(manifest)

    assert result.status == "ok"
    assert result.message == "registered (RRN not yet written)"
    assert result.detail == {"rrn": "", "exit_code": 0}


def test_ok_when_manifest_reparse_fails(tmp_path):
    """If the post-mint re-read raises, fall back to empty rrn rather than
    crashing the phase — the registration itself still succeeded.

    We patch cli_register last in the chain so the pre-mint parse_file + validate
    succeed, then the reparse at the tail fails via a side_effect swap.
    """
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n---\n")

    real_parse = __import__("robot_md.parser", fromlist=["parse_file"]).parse_file
    call_counter = {"n": 0}

    def _parse_side(p):
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            return real_parse(p)  # pre-mint parse succeeds
        raise RuntimeError("boom")  # post-mint reparse fails

    with (
        patch("robot_md.init_phases.register.validate_parsed", return_value=_mock_valid()),
        patch("robot_md.init_phases.register.parse_file", side_effect=_parse_side),
        patch("robot_md.init_phases.register.cli_register", return_value=0),
    ):
        result = phase_register(manifest)

    assert result.status == "ok"
    assert result.detail == {"rrn": "", "exit_code": 0}


def test_validate_failure_blocks_register(tmp_path):
    """If validation fails, phase_register returns failed WITHOUT calling cli_register."""
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n---\n")

    invalid = MagicMock()
    invalid.code = 5  # any non-VALID sentinel
    invalid.errors = ["missing required field: physics"]
    invalid.summary = "1 error"

    with (
        patch("robot_md.init_phases.register.validate_parsed", return_value=invalid),
        patch("robot_md.init_phases.register.cli_register") as run,
    ):
        result = phase_register(manifest)

    assert result.status == "failed"
    assert result.detail and result.detail.get("reason") == "validation_failed"
    run.assert_not_called()


def test_metadata_overrides_persisted_to_manifest(tmp_path):
    """--manufacturer / --model etc. must be written into the manifest
    before cli_register is called, so the registry and the file agree.
    """
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "metadata:\n"
        "  robot_name: bob\n"
        "  manufacturer: oldco\n"
        "  model: old-model\n"
        "---\n\n# bob\n"
    )

    captured: dict = {}

    def _capture_register(path, **kw):
        # cli_register is called AFTER the overrides write, so reading the
        # manifest here shows the post-override state.
        captured["after"] = Path(path).read_text()
        return 0

    with (
        patch("robot_md.init_phases.register.validate_parsed", return_value=_mock_valid()),
        patch("robot_md.init_phases.register.cli_register", side_effect=_capture_register),
    ):
        phase_register(manifest, manufacturer="acme", model="so-arm101")

    text = captured["after"]
    assert "manufacturer: acme" in text
    assert "model: so-arm101" in text
    assert "oldco" not in text
    assert "old-model" not in text


