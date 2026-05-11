"""Unit tests for robot-md trial subcommands."""

from __future__ import annotations

import importlib
import json

import pytest
from typer.testing import CliRunner


@pytest.fixture
def trial_home(tmp_path, monkeypatch):
    """Redirect ~/.robot-md/ to a temp dir for the test."""
    monkeypatch.setenv("HOME", str(tmp_path))
    import robot_md.trial as trial_mod

    importlib.reload(trial_mod)
    yield tmp_path


def test_trial_module_exposes_typer_app():
    import typer

    from robot_md.trial import trial_app

    assert isinstance(trial_app, typer.Typer)


def test_trials_dir_under_robot_md_home():
    from robot_md.trial import TRIALS_DIR

    assert TRIALS_DIR.name == "trials"
    assert TRIALS_DIR.parent.name == ".robot-md"


def test_cold_install_start_file_path():
    from robot_md.trial import COLD_INSTALL_START_FILE

    assert COLD_INSTALL_START_FILE.name == ".robot-md-cold-install-start.txt"


def test_trial_start_writes_start_json(trial_home):
    from robot_md.trial import trial_app

    runner = CliRunner()
    result = runner.invoke(trial_app, ["start", "--property", "bob.local/PICK-PLACE-10"])
    assert result.exit_code == 0, result.output

    trials = list((trial_home / ".robot-md" / "trials").iterdir())
    assert len(trials) == 1
    d = trials[0]
    assert d.name.startswith("trial_")
    assert (d / "frames").is_dir()

    state = json.loads((d / "start.json").read_text())
    assert state["property"] == "bob.local/PICK-PLACE-10"
    assert state["trial_id"] == d.name
    assert state["started_at"].endswith("Z")
    assert state["start_anchor"] == "robot_md_trial_start_only"  # no cold-install file
    assert state["cold_install_start_marker"] is None
    assert state["iterations"] == []
    assert state["aborted_at"] is None


def test_trial_start_reads_cold_install_marker(trial_home):
    from robot_md.trial import trial_app

    (trial_home / ".robot-md-cold-install-start.txt").write_text("2026-05-11T13:52:13Z\n")
    runner = CliRunner()
    result = runner.invoke(trial_app, ["start", "--property", "bob.local/PICK-PLACE-10"])
    assert result.exit_code == 0
    d = next((trial_home / ".robot-md" / "trials").iterdir())
    state = json.loads((d / "start.json").read_text())
    assert state["cold_install_start_marker"] == "2026-05-11T13:52:13Z"
    assert state["start_anchor"] == "claude_code_first_command"


def test_trial_start_ignores_malformed_cold_install_marker(trial_home):
    from robot_md.trial import trial_app

    (trial_home / ".robot-md-cold-install-start.txt").write_text("not-a-timestamp")
    runner = CliRunner()
    result = runner.invoke(trial_app, ["start", "--property", "bob.local/PICK-PLACE-10"])
    assert result.exit_code == 0
    d = next((trial_home / ".robot-md" / "trials").iterdir())
    state = json.loads((d / "start.json").read_text())
    assert state["cold_install_start_marker"] is None
    assert state["start_anchor"] == "robot_md_trial_start_only"


def test_trial_start_prints_trial_id_and_protocol(trial_home):
    from robot_md.trial import trial_app

    runner = CliRunner()
    result = runner.invoke(trial_app, ["start", "--property", "bob.local/PICK-PLACE-10"])
    assert "Trial ID: trial_" in result.output
    assert "--capture-pre" in result.output
    assert "--capture-post-and-verdict" in result.output
    assert "--reset-confirmed" in result.output
