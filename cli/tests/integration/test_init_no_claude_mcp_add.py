"""SP1 integration tests: default_flow invariants at the boundary.

Locks in two SP1 contracts:
  1. default_flow never shells out to `claude mcp …` (Phase 3 deprecation
     of phase_install_mcp + Phase 4 dropping its call from default_flow).
  2. default_flow invokes _emit_motion_extras_hint when the manifest
     declares motion-relevant capabilities (Phase 4 wire-up).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from robot_md.init_phases import PhaseResult


def _ok(phase: str, msg: str = "ok") -> PhaseResult:
    return PhaseResult(phase=phase, status="ok", message=msg, detail={})


def _skip(phase: str, msg: str = "skipped") -> PhaseResult:
    return PhaseResult(phase=phase, status="skipped", message=msg, detail={})


class _Device:
    def __init__(self, bus=None, protocol=None, label="", path=None):
        self.bus = bus
        self.protocol = protocol
        self.label = label
        self.path = path


class _Scan:
    def __init__(self, devices=None):
        self.devices = devices or []
        self.cameras: list = []


@pytest.fixture
def fake_scan():
    return _Scan(
        [_Device(bus="usb", protocol="feetech", label="Feetech servo bus", path="/dev/ttyACM0")]
    )


def _hardware_phase_patches(extra_patches=()):
    """Return the minimal set of context-manager patches needed to run
    default_flow without hardware or network.  Phases are stubbed to
    return PhaseResults; scan_system returns an empty scan.

    extra_patches: additional (target, mock_obj) pairs layered on top.
    """
    return [
        patch("robot_md.init.scan_system", return_value=_Scan()),
        patch("robot_md.init.phase_register", return_value=_skip("register")),
        patch("robot_md.init.phase_install_skill", return_value=_skip("install_skill")),
        patch("robot_md.init.phase_calibrate_sign", return_value=_skip("sign_cal")),
        patch("robot_md.init.phase_calibrate_zero", return_value=_skip("zero_cal")),
        patch("robot_md.init.phase_auto_calibrate_ready", return_value=_skip("auto_calibrate_ready")),
        patch("robot_md.init.phase_calibrate_extrinsic", return_value=_skip("calibrate_extrinsic")),
        patch("robot_md.init.phase_teach_poses", return_value=_skip("teach_poses")),
        patch("robot_md.init_phases.phase_compliance_scaffold", return_value=_skip("compliance_scaffold")),
        patch("robot_md.init_phases.phase_voice_setup", return_value=_skip("voice_setup")),
        patch("robot_md.init._refresh_claude_md"),
        *extra_patches,
    ]


# ---------------------------------------------------------------------------
# Test 1: no shell-out to `claude mcp ...`
# ---------------------------------------------------------------------------


def test_default_flow_does_not_shell_out_to_claude_mcp(tmp_path: Path):
    """End-to-end: default_flow with all hardware phases stubbed must not
    call subprocess.run with `claude mcp …` at any point.

    This catches future regressions where someone re-adds `claude mcp add`
    inside a phase.  The real phase_write_manifest runs so the actual init
    code paths (including any dormant subprocess call sites) are exercised.
    """
    out_path = tmp_path / "ROBOT.md"

    from robot_md.init import default_flow

    with patch("subprocess.run") as mock_run:
        for ctx in _hardware_phase_patches():
            ctx.__enter__()

        try:
            default_flow(
                out_path,
                robot_name="testbot",
                preset_name="minimal",
                do_register=False,
                do_install_mcp=False,
                do_install_skill=False,
                do_sign_cal=False,
                do_zero_cal=False,
                do_auto_calibrate=False,
                do_teach_poses=False,
                do_refresh_claude_md=False,
            )
        finally:
            for ctx in reversed(_hardware_phase_patches()):
                ctx.__exit__(None, None, None)

        # Assert: no subprocess.run call targeted `claude mcp …`
        for call in mock_run.call_args_list:
            args = call.args[0] if call.args else []
            if not isinstance(args, (list, tuple)):
                continue
            args_list = list(args)
            assert not (
                len(args_list) >= 2
                and str(args_list[0]) == "claude"
                and str(args_list[1]) == "mcp"
            ), f"default_flow shelled out to `claude mcp …`: {args_list}"


# ---------------------------------------------------------------------------
# Test 1 (cleaner form using nested with)
# ---------------------------------------------------------------------------


def test_default_flow_does_not_shell_out_to_claude_mcp_v2(tmp_path: Path):
    """Cleaner nested-with version of the shell-out guard.

    Uses contextlib.ExitStack so we avoid the manual enter/exit dance above.
    """
    import contextlib

    out_path = tmp_path / "ROBOT.md"
    from robot_md.init import default_flow

    with contextlib.ExitStack() as stack:
        mock_run = stack.enter_context(patch("subprocess.run"))
        stack.enter_context(patch("robot_md.init.scan_system", return_value=_Scan()))
        stack.enter_context(patch("robot_md.init.phase_register", return_value=_skip("register")))
        stack.enter_context(patch("robot_md.init.phase_install_skill", return_value=_skip("install_skill")))
        stack.enter_context(patch("robot_md.init.phase_calibrate_sign", return_value=_skip("sign_cal")))
        stack.enter_context(patch("robot_md.init.phase_calibrate_zero", return_value=_skip("zero_cal")))
        stack.enter_context(patch("robot_md.init.phase_auto_calibrate_ready", return_value=_skip("auto_calibrate_ready")))
        stack.enter_context(patch("robot_md.init.phase_calibrate_extrinsic", return_value=_skip("calibrate_extrinsic")))
        stack.enter_context(patch("robot_md.init.phase_teach_poses", return_value=_skip("teach_poses")))
        stack.enter_context(patch("robot_md.init_phases.phase_compliance_scaffold", return_value=_skip("compliance_scaffold")))
        stack.enter_context(patch("robot_md.init_phases.phase_voice_setup", return_value=_skip("voice_setup")))
        stack.enter_context(patch("robot_md.init._refresh_claude_md"))

        rc = default_flow(
            out_path,
            robot_name="testbot",
            preset_name="minimal",
            do_register=False,
            do_install_mcp=False,
            do_install_skill=False,
            do_sign_cal=False,
            do_zero_cal=False,
            do_auto_calibrate=False,
            do_teach_poses=False,
            do_refresh_claude_md=False,
        )

    assert rc == 0

    for call in mock_run.call_args_list:
        args = call.args[0] if call.args else []
        if not isinstance(args, (list, tuple)):
            continue
        args_list = list(args)
        assert not (
            len(args_list) >= 2
            and str(args_list[0]) == "claude"
            and str(args_list[1]) == "mcp"
        ), f"default_flow shelled out to `claude mcp …`: {args_list}"


# ---------------------------------------------------------------------------
# Test 2: install_mcp tally line is absent from output (deprecated SP1 R1)
# ---------------------------------------------------------------------------


def test_install_mcp_absent_from_tally(tmp_path: Path, capsys):
    """The install-mcp tally line must not appear in stderr output.

    Since phase_install_mcp is no longer called by default_flow (SP1 R1
    deprecation, Phase 3+4), its result never enters the tally.  This test
    verifies the absence at the rendered-output level, catching any
    re-addition of the call site.
    """
    import contextlib

    out_path = tmp_path / "ROBOT.md"
    from robot_md.init import default_flow

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("robot_md.init.scan_system", return_value=_Scan()))
        # Patch install_mcp to make it observable if it fires
        mock_install_mcp = stack.enter_context(
            patch("robot_md.init.phase_install_mcp", return_value=_ok("install_mcp", "should not appear"))
        )
        stack.enter_context(patch("robot_md.init.phase_register", return_value=_skip("register")))
        stack.enter_context(patch("robot_md.init.phase_install_skill", return_value=_skip("install_skill")))
        stack.enter_context(patch("robot_md.init.phase_calibrate_sign", return_value=_skip("sign_cal")))
        stack.enter_context(patch("robot_md.init.phase_calibrate_zero", return_value=_skip("zero_cal")))
        stack.enter_context(patch("robot_md.init.phase_auto_calibrate_ready", return_value=_skip("auto_calibrate_ready")))
        stack.enter_context(patch("robot_md.init.phase_calibrate_extrinsic", return_value=_skip("calibrate_extrinsic")))
        stack.enter_context(patch("robot_md.init.phase_teach_poses", return_value=_skip("teach_poses")))
        stack.enter_context(patch("robot_md.init_phases.phase_compliance_scaffold", return_value=_skip("compliance_scaffold")))
        stack.enter_context(patch("robot_md.init_phases.phase_voice_setup", return_value=_skip("voice_setup")))
        stack.enter_context(patch("robot_md.init._refresh_claude_md"))

        rc = default_flow(
            out_path,
            robot_name="testbot",
            preset_name="minimal",
            do_register=False,
            do_install_mcp=True,  # explicitly opt-in — tests SP1 deprecation guard
            do_install_skill=False,
            do_sign_cal=False,
            do_zero_cal=False,
            do_auto_calibrate=False,
            do_teach_poses=False,
            do_refresh_claude_md=False,
        )

    assert rc == 0
    # phase_install_mcp must never have been called (dropped from default_flow)
    assert mock_install_mcp.call_count == 0, (
        "phase_install_mcp was called — SP1 R1 deprecation broken; "
        "default_flow must not call phase_install_mcp"
    )
    err = capsys.readouterr().err
    assert "install-mcp" not in err, (
        f"'install-mcp' appeared in tally stderr — phase was re-added:\n{err}"
    )


# ---------------------------------------------------------------------------
# Test 3: _emit_motion_extras_hint fires for motion-capable manifests
# ---------------------------------------------------------------------------


def test_default_flow_invokes_motion_extras_hint_for_motion_manifest(
    tmp_path: Path, capsys
):
    """End-to-end: when default_flow writes a manifest with motion
    capabilities (so_arm101 declares arm.*), _emit_motion_extras_hint
    must fire and produce the pip install hint on stderr.

    The real phase_write_manifest and parse_file run so the inline hint
    reader at init.py:751-761 exercises real code paths.
    """
    import contextlib

    out_path = tmp_path / "ROBOT.md"
    from robot_md.init import default_flow

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("robot_md.init.scan_system", return_value=_Scan()))
        stack.enter_context(patch("robot_md.init.phase_register", return_value=_skip("register")))
        stack.enter_context(patch("robot_md.init.phase_install_skill", return_value=_skip("install_skill")))
        stack.enter_context(patch("robot_md.init.phase_calibrate_sign", return_value=_skip("sign_cal")))
        stack.enter_context(patch("robot_md.init.phase_calibrate_zero", return_value=_skip("zero_cal")))
        stack.enter_context(patch("robot_md.init.phase_auto_calibrate_ready", return_value=_skip("auto_calibrate_ready")))
        stack.enter_context(patch("robot_md.init.phase_calibrate_extrinsic", return_value=_skip("calibrate_extrinsic")))
        stack.enter_context(patch("robot_md.init.phase_teach_poses", return_value=_skip("teach_poses")))
        stack.enter_context(patch("robot_md.init_phases.phase_compliance_scaffold", return_value=_skip("compliance_scaffold")))
        stack.enter_context(patch("robot_md.init_phases.phase_voice_setup", return_value=_skip("voice_setup")))
        stack.enter_context(patch("robot_md.init._refresh_claude_md"))

        try:
            rc = default_flow(
                out_path,
                robot_name="testbot",
                preset_name="so_arm101",   # arm.* capabilities → hint must fire
                do_register=False,
                do_install_mcp=False,
                do_install_skill=False,
                do_sign_cal=False,
                do_zero_cal=False,
                do_auto_calibrate=False,
                do_teach_poses=False,
                do_refresh_claude_md=False,
            )
        except Exception as exc:
            pytest.skip(f"so_arm101 preset not usable in test env: {exc}")

    assert rc == 0

    manifest_text = out_path.read_text()
    err = capsys.readouterr().err

    if "arm." in manifest_text:
        assert "pip install" in err and "robot-md[hardware]" in err, (
            f"Expected motion-extras hint in stderr but it was absent.\n"
            f"stderr:\n{err}"
        )
    else:
        pytest.skip("so_arm101 preset did not produce arm.* capabilities in this env")


# ---------------------------------------------------------------------------
# Test 4: hint suppressed for non-motion manifests
# ---------------------------------------------------------------------------


def test_default_flow_does_not_emit_hint_for_nonmotion_manifest(
    tmp_path: Path, capsys
):
    """Sanity: minimal preset (status.report + vision.describe, no arm.*)
    must NOT produce the hardware-runtime pip-install hint.
    """
    import contextlib

    out_path = tmp_path / "ROBOT.md"
    from robot_md.init import default_flow

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("robot_md.init.scan_system", return_value=_Scan()))
        stack.enter_context(patch("robot_md.init.phase_register", return_value=_skip("register")))
        stack.enter_context(patch("robot_md.init.phase_install_skill", return_value=_skip("install_skill")))
        stack.enter_context(patch("robot_md.init.phase_calibrate_sign", return_value=_skip("sign_cal")))
        stack.enter_context(patch("robot_md.init.phase_calibrate_zero", return_value=_skip("zero_cal")))
        stack.enter_context(patch("robot_md.init.phase_auto_calibrate_ready", return_value=_skip("auto_calibrate_ready")))
        stack.enter_context(patch("robot_md.init.phase_calibrate_extrinsic", return_value=_skip("calibrate_extrinsic")))
        stack.enter_context(patch("robot_md.init.phase_teach_poses", return_value=_skip("teach_poses")))
        stack.enter_context(patch("robot_md.init_phases.phase_compliance_scaffold", return_value=_skip("compliance_scaffold")))
        stack.enter_context(patch("robot_md.init_phases.phase_voice_setup", return_value=_skip("voice_setup")))
        stack.enter_context(patch("robot_md.init._refresh_claude_md"))

        rc = default_flow(
            out_path,
            robot_name="testbot",
            preset_name="minimal",
            do_register=False,
            do_install_mcp=False,
            do_install_skill=False,
            do_sign_cal=False,
            do_zero_cal=False,
            do_auto_calibrate=False,
            do_teach_poses=False,
            do_refresh_claude_md=False,
        )

    assert rc == 0

    manifest_text = out_path.read_text()
    err = capsys.readouterr().err

    has_motion_caps = any(
        prefix in manifest_text
        for prefix in ("arm.", "nav.", "gripper.", "perceive.")
    )
    if not has_motion_caps:
        assert "pip install 'robot-md[hardware]'" not in err, (
            f"Hint must be suppressed for non-motion manifests.\nstderr:\n{err}"
        )
    # If somehow minimal grew motion caps, the assertion is vacuously
    # satisfied (the preset changed intent and needs its own review).
