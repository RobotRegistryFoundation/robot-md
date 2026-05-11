"""Unit tests for robot-md trial subcommands."""
from __future__ import annotations

import importlib

import pytest


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
