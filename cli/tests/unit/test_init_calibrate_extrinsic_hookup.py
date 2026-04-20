"""Task 16: verify phase_calibrate_extrinsic is wired into default_flow.

The phase must be invoked on every init path (including non-interactive /
no-hardware runs) so it can return its own 'skipped' result — the ordering
contract is visible to other phases (e.g., doctor warns on preset_default).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from robot_md.init_phases import PhaseResult


# ---------------------------------------------------------------------------
# helpers (mirrored from test_init_auto_calibrate_ready.py)
# ---------------------------------------------------------------------------


def _ok_factory(phase_label: str):
    def _fn(*a, **kw):
        return PhaseResult(phase=phase_label, status="ok", message="", detail={})

    return _fn


def _skip_factory(phase_label: str):
    def _fn(*a, **kw):
        return PhaseResult(phase=phase_label, status="skipped", message="", detail={})

    return _fn


def _patch_other_phases(monkeypatch, init_module):
    """Stub every phase except phase_calibrate_extrinsic.

    phase_write_manifest must return status="ok" or default_flow aborts
    early (before the extrinsic phase is ever reached).
    """
    monkeypatch.setattr(
        init_module,
        "phase_write_manifest",
        _ok_factory("write_manifest"),
        raising=False,
    )
    for name in (
        "phase_calibrate_sign",
        "phase_calibrate_zero",
        "phase_auto_calibrate_ready",
        "phase_teach_poses",
    ):
        monkeypatch.setattr(
            init_module,
            name,
            _skip_factory(name.replace("phase_", "")),
            raising=False,
        )


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_default_flow_invokes_calibrate_extrinsic_phase(tmp_path, monkeypatch):
    """default_flow must call phase_calibrate_extrinsic on every run."""
    from robot_md import init

    calls: dict[str, int] = {"count": 0}

    def fake_phase(manifest_path, *, bus, camera, interactive):
        calls["count"] += 1
        # Mimic the skip that happens when bus=None (no hardware in default_flow)
        return PhaseResult(
            phase="calibrate_extrinsic",
            status="skipped",
            message="no actuatable bus",
            detail={"reason": "no_actuatable_bus"},
        )

    monkeypatch.setattr(init, "phase_calibrate_extrinsic", fake_phase, raising=False)
    _patch_other_phases(monkeypatch, init)

    out = tmp_path / "ROBOT.md"
    out.write_text("---\nmetadata:\n  robot_name: r\n---\n\n# r\n\n")

    init.default_flow(
        out,
        robot_name="r",
        preset_name="so-arm101",
        do_install_mcp=False,
        do_install_skill=False,
        do_register=False,
        do_refresh_claude_md=False,
    )

    assert calls["count"] == 1, (
        "phase_calibrate_extrinsic must be called exactly once by default_flow"
    )


def test_default_flow_passes_none_bus_and_camera(tmp_path, monkeypatch):
    """default_flow opens no hardware, so bus and camera must both be None."""
    from robot_md import init

    received: dict = {}

    def fake_phase(manifest_path, *, bus, camera, interactive):
        received["bus"] = bus
        received["camera"] = camera
        return PhaseResult(
            phase="calibrate_extrinsic",
            status="skipped",
            message="no actuatable bus",
            detail={"reason": "no_actuatable_bus"},
        )

    monkeypatch.setattr(init, "phase_calibrate_extrinsic", fake_phase, raising=False)
    _patch_other_phases(monkeypatch, init)

    out = tmp_path / "ROBOT.md"
    out.write_text("---\nmetadata:\n  robot_name: r\n---\n\n# r\n\n")

    init.default_flow(
        out,
        robot_name="r",
        preset_name="so-arm101",
        do_install_mcp=False,
        do_install_skill=False,
        do_register=False,
        do_refresh_claude_md=False,
    )

    assert received.get("bus") is None, "bus must be None (default_flow opens no hardware)"
    assert received.get("camera") is None, "camera must be None (default_flow opens no hardware)"


def test_non_interactive_invokes_calibrate_extrinsic_phase_with_skip(tmp_path, monkeypatch):
    """Non-interactive init (via default_flow) must still CALL phase_calibrate_extrinsic
    so the phase can return its 'skipped: non_interactive' result — the ordering
    contract is visible to other phases (e.g., doctor warns on preset_default).
    """
    from robot_md import init

    calls: dict[str, int] = {"count": 0}

    def fake_phase(manifest_path, *, bus, camera, interactive):
        calls["count"] += 1
        return PhaseResult(
            phase="calibrate_extrinsic",
            status="skipped",
            message="non-interactive",
            detail={"reason": "non_interactive"},
        )

    monkeypatch.setattr(init, "phase_calibrate_extrinsic", fake_phase, raising=False)
    _patch_other_phases(monkeypatch, init)

    out = tmp_path / "ROBOT.md"
    out.write_text("---\nmetadata:\n  robot_name: r\n---\n\n# r\n\n")

    # Simulate non-interactive: stdin.isatty() → False (already the default in tests)
    init.default_flow(
        out,
        robot_name="r",
        preset_name="so-arm101",
        do_install_mcp=False,
        do_install_skill=False,
        do_register=False,
        do_refresh_claude_md=False,
    )

    assert calls["count"] == 1, (
        "phase_calibrate_extrinsic must be called even in non-interactive runs"
    )
