"""`robot-md init --non-interactive` preserves the old quick() behavior.

This is the scripted-caller / CI compatibility test. It must keep passing
after Task 10 wires default_flow into __main__.py.
"""

from __future__ import annotations

from typer.testing import CliRunner

from robot_md.__main__ import app


def test_non_interactive_writes_manifest_only(tmp_path, monkeypatch):
    runner = CliRunner()
    out = tmp_path / "ROBOT.md"

    # Prevent any network or hardware access by patching the optional phases
    # to raise if they're called — the test asserts they aren't.
    import robot_md.init as init_mod

    monkeypatch.setattr(
        init_mod,
        "phase_install_mcp",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("install_mcp should not run")),
    )
    monkeypatch.setattr(
        init_mod,
        "phase_install_skill",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("install_skill should not run")),
    )
    monkeypatch.setattr(
        init_mod,
        "phase_calibrate_sign",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("sign_cal should not run")),
    )
    monkeypatch.setattr(
        init_mod,
        "phase_calibrate_zero",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("zero_cal should not run")),
    )

    result = runner.invoke(
        app,
        [
            "init",
            "bob",
            "--preset",
            "so-arm101",
            "--out",
            str(out),
            "--non-interactive",
            "--no-claude-md",
        ],
    )

    # click 8.x: result.stderr raises ValueError when stderr isn't separately
    # captured. Access stderr_bytes directly to stay resilient.
    err_detail = result.output + ((result.stderr_bytes or b"").decode("utf-8", "replace"))
    assert result.exit_code == 0, err_detail
    assert out.exists()
    text = out.read_text()
    assert "bob" in text
