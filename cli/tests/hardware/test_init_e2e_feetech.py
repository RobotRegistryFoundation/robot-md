"""End-to-end init smoke test against a real SO-ARM101.

Opt-in: requires env var ROBOT_MD_HARDWARE=1 and a plugged-in arm on
/dev/ttyACM0. Not run in default CI.
"""

from __future__ import annotations

import os

import pytest
from typer.testing import CliRunner

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(
        os.environ.get("ROBOT_MD_HARDWARE") != "1",
        reason="hardware smoke test; set ROBOT_MD_HARDWARE=1 with arm plugged in",
    ),
]


def test_default_flow_writes_calibrated_manifest(tmp_path, monkeypatch):
    """A full init run should write ROBOT.md AND patch zero_pose_steps
    to the reading observed on the connected arm."""
    from robot_md.__main__ import app

    runner = CliRunner()
    out = tmp_path / "ROBOT.md"

    # Force yes-answers to the Y/n prompts; no actual skill install
    # (we don't want to touch ~/.claude/skills/ in a smoke test).
    monkeypatch.setattr("builtins.input", lambda *_: "y")

    result = runner.invoke(
        app,
        [
            "init",
            "bob-smoke",
            "--preset",
            "so-arm101",
            "--out",
            str(out),
            "--no-install-mcp",
            "--no-install-skill",
            "--no-sign",  # sign wiggles joints — keep zero-only to minimize motion
            "--no-claude-md",
        ],
    )

    assert result.exit_code == 0, result.output
    assert out.exists()
    text = out.read_text()
    # Zero pose should no longer be the default 2048 for every joint.
    # At least one joint's reading should differ from 2048 unless the
    # operator poses it at exactly 2048 on every encoder, which is
    # vanishingly unlikely.
    import yaml

    fm = yaml.safe_load(text.split("---", 2)[1])
    values = [j.get("zero_pose_steps") for j in fm["physics"]["kinematics"]]
    assert any(v != 2048 for v in values), (
        "expected at least one joint's zero_pose_steps to differ from the "
        "preset default after calibration"
    )
