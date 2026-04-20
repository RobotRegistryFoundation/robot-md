"""Phase must skip cleanly in non-interactive, no-camera, no-bus, and
already-calibrated cases."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from robot_md.init_phases import phase_calibrate_extrinsic


def _manifest(tmp_path: Path, extrinsic_source: str = "preset_default") -> Path:
    p = tmp_path / "ROBOT.md"
    p.write_text(
        "---\n"
        "metadata:\n  robot_name: bob\n"
        "physics:\n"
        "  workspace:\n    bounds_mm:\n      x: [-200, 340]\n      y: [-340, 340]\n      z: [0, 250]\n"
        "  solver:\n    cameras:\n"
        f"      - driver_id: oakd\n        extrinsic: [400.0, 0.0, 300.0, -2.55, 0.0, 1.57]\n        extrinsic_source: {extrinsic_source}\n"
        "---\n\n# bob\n"
    )
    return p


def test_skip_when_non_interactive(tmp_path):
    result = phase_calibrate_extrinsic(
        _manifest(tmp_path),
        bus=MagicMock(),
        camera=MagicMock(),
        interactive=False,
    )
    assert result.status == "skipped"
    assert result.detail["reason"] == "non_interactive"


def test_skip_when_no_camera(tmp_path):
    result = phase_calibrate_extrinsic(
        _manifest(tmp_path),
        bus=MagicMock(),
        camera=None,
        interactive=True,
    )
    assert result.status == "skipped"
    assert result.detail["reason"] == "no_camera"


def test_skip_when_no_bus(tmp_path):
    result = phase_calibrate_extrinsic(
        _manifest(tmp_path),
        bus=None,
        camera=MagicMock(),
        interactive=True,
    )
    assert result.status == "skipped"
    assert result.detail["reason"] == "no_actuatable_bus"


def test_skip_when_already_calibrated(tmp_path):
    result = phase_calibrate_extrinsic(
        _manifest(tmp_path, extrinsic_source="gripper_silhouette_calibrated"),
        bus=MagicMock(),
        camera=MagicMock(),
        interactive=True,
    )
    assert result.status == "skipped"
    assert result.detail["reason"] == "already_calibrated"


def test_skip_when_user_declines(tmp_path, monkeypatch):
    """Interactive prompt replied 'n' → skip."""
    monkeypatch.setattr("builtins.input", lambda _prompt="": "n")
    result = phase_calibrate_extrinsic(
        _manifest(tmp_path),
        bus=MagicMock(),
        camera=MagicMock(),
        interactive=True,
    )
    assert result.status == "skipped"
    assert result.detail["reason"] == "declined"
