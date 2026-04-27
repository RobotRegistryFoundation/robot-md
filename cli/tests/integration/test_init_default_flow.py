"""Integration tests for the init orchestrator — all phases mocked."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from robot_md.init_phases import PhaseResult


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


def _ok(phase, msg="ok"):
    return PhaseResult(phase=phase, status="ok", message=msg, detail={})


def _skip(phase, msg="skipped"):
    return PhaseResult(phase=phase, status="skipped", message=msg, detail={})


def _fail(phase, msg="failed"):
    return PhaseResult(phase=phase, status="failed", message=msg, detail={})


@pytest.fixture
def fake_scan():
    return _Scan(
        [_Device(bus="usb", protocol="feetech", label="Feetech servo bus", path="/dev/ttyACM0")]
    )


def test_default_flow_runs_all_phases_in_order(tmp_path, fake_scan):
    from robot_md.init import default_flow

    out = tmp_path / "ROBOT.md"
    calls: list[str] = []

    def _track(name, status="ok"):
        def fn(*a, **kw):
            calls.append(name)
            return _ok(name) if status == "ok" else _skip(name)

        return fn

    with (
        patch("robot_md.init.scan_system", return_value=fake_scan),
        patch("robot_md.init.phase_write_manifest", side_effect=_track("write_manifest")),
        patch("robot_md.init.phase_register", side_effect=_track("register")),
        patch("robot_md.init.phase_install_mcp", side_effect=_track("install_mcp")),
        patch("robot_md.init.phase_install_skill", side_effect=_track("install_skill")),
        patch("robot_md.init.phase_calibrate_sign", side_effect=_track("sign_cal")),
        patch("robot_md.init.phase_calibrate_zero", side_effect=_track("zero_cal")),
        patch("robot_md.init._refresh_claude_md"),
    ):
        rc = default_flow(
            out,
            robot_name="bob",
            preset_name="so-arm101",
            force=False,
            do_register=True,
            contact_email="me@acme.com",
            do_install_mcp=True,
            do_install_skill=True,
            do_sign_cal=True,
            do_zero_cal=True,
        )

    assert rc == 0
    # install_mcp deprecated per SP1 R1 — no longer called by default_flow.
    assert calls == [
        "write_manifest",
        "register",
        "install_skill",
        "sign_cal",
        "zero_cal",
    ]


def test_write_manifest_failure_aborts(tmp_path, fake_scan):
    from robot_md.init import default_flow

    out = tmp_path / "ROBOT.md"
    other_called: list[str] = []

    def _track(name):
        def fn(*a, **kw):
            other_called.append(name)
            return _ok(name)

        return fn

    with (
        patch("robot_md.init.scan_system", return_value=fake_scan),
        patch("robot_md.init.phase_write_manifest", return_value=_fail("write_manifest")),
        patch("robot_md.init.phase_register", side_effect=_track("register")),
        patch("robot_md.init.phase_install_mcp", side_effect=_track("install_mcp")),
        patch("robot_md.init.phase_install_skill", side_effect=_track("install_skill")),
        patch("robot_md.init.phase_calibrate_sign", side_effect=_track("sign_cal")),
        patch("robot_md.init.phase_calibrate_zero", side_effect=_track("zero_cal")),
        patch("robot_md.init._refresh_claude_md"),
    ):
        rc = default_flow(
            out,
            robot_name="bob",
            preset_name="so-arm101",
            force=False,
            do_register=True,
            do_install_mcp=True,
            do_install_skill=True,
            do_sign_cal=True,
            do_zero_cal=True,
        )

    assert rc != 0
    assert other_called == []


def test_non_fatal_failures_continue_and_exit_zero(tmp_path, fake_scan):
    from robot_md.init import default_flow

    out = tmp_path / "ROBOT.md"

    with (
        patch("robot_md.init.scan_system", return_value=fake_scan),
        patch("robot_md.init.phase_write_manifest", return_value=_ok("write_manifest")),
        patch("robot_md.init.phase_install_mcp", return_value=_fail("install_mcp")),
        patch("robot_md.init.phase_install_skill", return_value=_ok("install_skill")),
        patch("robot_md.init.phase_calibrate_sign", return_value=_skip("sign_cal")),
        patch("robot_md.init.phase_calibrate_zero", return_value=_fail("zero_cal")),
        patch("robot_md.init._refresh_claude_md"),
    ):
        rc = default_flow(
            out,
            robot_name="bob",
            preset_name="so-arm101",
            force=False,
            do_register=False,
            do_install_mcp=True,
            do_install_skill=True,
            do_sign_cal=True,
            do_zero_cal=True,
        )

    assert rc == 0


def test_skip_flags_omit_phases(tmp_path, fake_scan):
    from robot_md.init import default_flow

    out = tmp_path / "ROBOT.md"
    calls: list[str] = []

    def _rec(name):
        def fn(*a, **kw):
            calls.append(name)
            return _ok(name)

        return fn

    with (
        patch("robot_md.init.scan_system", return_value=fake_scan),
        patch("robot_md.init.phase_write_manifest", side_effect=_rec("write_manifest")),
        patch("robot_md.init.phase_register", side_effect=_rec("register")),
        patch("robot_md.init.phase_install_mcp", side_effect=_rec("install_mcp")),
        patch("robot_md.init.phase_install_skill", side_effect=_rec("install_skill")),
        patch("robot_md.init.phase_calibrate_sign", side_effect=_rec("sign_cal")),
        patch("robot_md.init.phase_calibrate_zero", side_effect=_rec("zero_cal")),
        patch("robot_md.init._refresh_claude_md"),
    ):
        default_flow(
            out,
            robot_name="bob",
            preset_name="so-arm101",
            force=False,
            do_register=False,
            do_install_mcp=False,
            do_install_skill=False,
            do_sign_cal=False,
            do_zero_cal=False,
        )

    assert calls == ["write_manifest"]


def test_tally_prints_one_line_per_executed_phase(tmp_path, fake_scan, capsys):
    from robot_md.init import default_flow

    out = tmp_path / "ROBOT.md"

    _mcp_msg = "registered 'robot-md-bob'"
    _zero_msg = "zero_pose_steps patched"
    with (
        patch("robot_md.init.scan_system", return_value=fake_scan),
        patch(
            "robot_md.init.phase_write_manifest",
            return_value=_ok("write_manifest", "wrote ROBOT.md"),
        ),
        patch(
            "robot_md.init.phase_install_mcp",
            return_value=_ok("install_mcp", _mcp_msg),
        ),
        patch(
            "robot_md.init.phase_install_skill",
            return_value=_ok("install_skill", "installed"),
        ),
        patch(
            "robot_md.init.phase_calibrate_sign",
            return_value=_skip("sign_cal", "operator declined"),
        ),
        patch(
            "robot_md.init.phase_calibrate_zero",
            return_value=_ok("zero_cal", _zero_msg),
        ),
        patch("robot_md.init._refresh_claude_md"),
    ):
        default_flow(
            out,
            robot_name="bob",
            preset_name="so-arm101",
            force=False,
            do_register=False,
            do_install_mcp=True,
            do_install_skill=True,
            do_sign_cal=True,
            do_zero_cal=True,
        )

    err = capsys.readouterr().err
    assert "✓ manifest" in err
    # install-mcp deprecated per SP1 R1 — no longer appears in tally.
    assert "install-skill" in err
    assert "sign-cal" in err
    assert "zero-cal" in err
    # Skipped prefix
    assert "-" in err  # dash for skipped


def test_claude_md_refresh_runs_after_register_so_rrn_is_not_stale(tmp_path, fake_scan):
    """The generated CLAUDE.md must include the minted RRN, not '(unregistered)'.

    Regression test for a bug where _refresh_claude_md ran before phase_register,
    so the marketing one-liner `init --register ...` left CLAUDE.md showing
    "Registered RRN: (unregistered)" even when the mint succeeded.
    """
    from robot_md.init import default_flow

    out = tmp_path / "ROBOT.md"

    def _fake_register(*_, **__):
        # phase_register normally calls cli_register which writes metadata.rrn.
        # Simulate that by patching the freshly-written manifest in place.
        from ruamel.yaml import YAML

        text = out.read_text()
        end = text.find("\n---", 3)
        fm_text = text[3:end].lstrip("\n")
        body = text[end + 4 :]
        y = YAML()
        y.preserve_quotes = True
        y.indent(mapping=2, sequence=4, offset=2)
        data = y.load(fm_text)
        data.setdefault("metadata", {})["rrn"] = "RRN-ABC123456789"
        import io

        buf = io.StringIO()
        y.dump(data, buf)
        out.write_text("---\n" + buf.getvalue().rstrip("\n") + "\n---" + body)
        return PhaseResult(
            phase="register",
            status="ok",
            message="minted RRN-ABC123456789",
            detail={"rrn": "RRN-ABC123456789", "exit_code": 0},
        )

    with (
        patch("robot_md.init.scan_system", return_value=fake_scan),
        patch("robot_md.init.phase_register", side_effect=_fake_register),
        patch("robot_md.init.phase_install_mcp", return_value=_ok("install_mcp")),
        patch("robot_md.init.phase_install_skill", return_value=_ok("install_skill")),
        patch("robot_md.init.phase_calibrate_sign", return_value=_skip("sign_cal")),
        patch("robot_md.init.phase_calibrate_zero", return_value=_skip("zero_cal")),
    ):
        # Real write_manifest + real _refresh_claude_md — only the phase mocks
        # that shortcut network / hardware / skill-install side effects.
        rc = default_flow(
            out,
            robot_name="bob",
            preset_name="so-arm101",
            force=False,
            do_register=True,
            contact_email="me@acme.com",
            do_install_mcp=True,
            do_install_skill=True,
            do_sign_cal=True,
            do_zero_cal=True,
        )

    assert rc == 0
    claude_md = (tmp_path / "CLAUDE.md").read_text()
    assert "RRN-ABC123456789" in claude_md, (
        f"CLAUDE.md should contain the minted RRN; got:\n{claude_md}"
    )
    assert "(unregistered)" not in claude_md
