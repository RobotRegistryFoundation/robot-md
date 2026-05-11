"""Unit tests for robot-md trial subcommands."""

from __future__ import annotations

import importlib
import json
import pathlib

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_trial(trial_home: pathlib.Path, trial_id: str = "trial_abc123") -> pathlib.Path:
    d = trial_home / ".robot-md" / "trials" / trial_id
    d.mkdir(parents=True)
    (d / "frames").mkdir()
    state = {
        "trial_id": trial_id,
        "property": "bob.local/PICK-PLACE-10",
        "started_at": "2026-05-11T14:00:00Z",
        "cold_install_start_marker": None,
        "start_anchor": "robot_md_trial_start_only",
        "iterations": [],
        "aborted_at": None,
    }
    (d / "start.json").write_text(json.dumps(state) + "\n")
    return d


# ---------------------------------------------------------------------------
# --capture-pre tests
# ---------------------------------------------------------------------------


def test_capture_pre_writes_iter_json_with_perceive_results(trial_home, monkeypatch):
    from robot_md.trial import trial_app

    d = _seed_trial(trial_home)

    def _fake_invoke(actuator: str, tool: str, args: dict) -> dict:
        if actuator == "oak-d" and args.get("query") == "red_blob":
            return {
                "actuator_name": "oak-d",
                "outcome_kind": "executed",
                "telemetry": {
                    "found": True,
                    "centroid_px": [612, 358],
                    "centroid_depth_mm": 327,
                    "bbox_px": [598, 344, 626, 372],
                    "pixel_count": 478,
                    "provenance": {},
                },
            }
        if actuator == "oak-d" and args.get("query") == "bowl_top":
            return {
                "actuator_name": "oak-d",
                "outcome_kind": "executed",
                "telemetry": {
                    "found": True,
                    "centroid_px": [285, 412],
                    "centroid_depth_mm": 305,
                    "bbox_px": [220, 350, 350, 470],
                    "pixel_count": 9412,
                    "provenance": {},
                },
            }
        if actuator == "so-arm101" and tool == "read_state":
            return {
                "actuator_name": "so-arm101",
                "outcome_kind": "executed",
                "telemetry": {
                    "positions": {
                        "shoulder_pan": 0.0,
                        "shoulder_lift": 0.1,
                        "elbow_flex": 0.0,
                        "wrist_flex": 0.0,
                        "wrist_roll": 0.0,
                        "gripper": 0.0,
                    }
                },
            }
        raise AssertionError(f"unexpected: {actuator}/{tool}/{args}")

    monkeypatch.setattr("robot_md.trial._gateway_invoke", _fake_invoke)

    runner = CliRunner()
    result = runner.invoke(trial_app, ["iteration", "--trial", d.name, "--capture-pre"])
    assert result.exit_code == 0, result.output

    iter_file = d / "iter_1.json"
    assert iter_file.exists()
    iter1 = json.loads(iter_file.read_text())
    assert iter1["iteration"] == 1
    assert iter1["pre_state"]["perceive_red_blob"]["found"] is True
    assert iter1["pre_state"]["perceive_red_blob"]["centroid_px"] == [612, 358]
    assert iter1["pre_state"]["perceive_bowl_top"]["found"] is True
    assert iter1["pre_state"]["joint_positions_rad"]["gripper"] == 0.0
    assert iter1["started_at"].endswith("Z")


def test_capture_pre_increments_iteration_number(trial_home, monkeypatch):
    from robot_md.trial import trial_app

    d = _seed_trial(trial_home)
    (d / "iter_1.json").write_text("{}\n")
    (d / "iter_2.json").write_text("{}\n")

    def _fake_invoke(actuator: str, tool: str, args: dict) -> dict:
        return {"telemetry": {"found": False, "positions": {}}}

    monkeypatch.setattr("robot_md.trial._gateway_invoke", _fake_invoke)

    runner = CliRunner()
    result = runner.invoke(trial_app, ["iteration", "--trial", d.name, "--capture-pre"])
    assert result.exit_code == 0, result.output

    iter3_file = d / "iter_3.json"
    assert iter3_file.exists()
    iter3 = json.loads(iter3_file.read_text())
    assert iter3["iteration"] == 3


def test_capture_pre_rejects_unknown_trial(trial_home):
    from robot_md.trial import trial_app

    runner = CliRunner()
    result = runner.invoke(trial_app, ["iteration", "--trial", "trial_nope", "--capture-pre"])
    assert result.exit_code != 0
    assert "unknown trial" in result.output.lower()


# ---------------------------------------------------------------------------
# --capture-post-and-verdict helpers + tests
# ---------------------------------------------------------------------------


def _seed_iter_pre(d: pathlib.Path, iter_num: int = 1) -> None:
    iter_state = {
        "iteration": iter_num,
        "started_at": "2026-05-11T14:01:00Z",
        "pre_state": {
            "joint_positions_rad": {"gripper": 0.0},
            "perceive_red_blob": {
                "found": True,
                "centroid_px": [612, 358],
                "centroid_depth_mm": 327,
                "bbox_px": [598, 344, 626, 372],
                "pixel_count": 478,
                "provenance": {},
            },
            "perceive_bowl_top": {
                "found": True,
                "centroid_px": [285, 412],
                "centroid_depth_mm": 305,
                "bbox_px": [220, 350, 350, 470],
                "pixel_count": 9412,
                "provenance": {},
            },
        },
    }
    (d / f"iter_{iter_num}.json").write_text(json.dumps(iter_state) + "\n")


def test_capture_post_marks_pass_when_red_inside_bowl(trial_home, monkeypatch):
    from robot_md.trial import trial_app

    d = _seed_trial(trial_home)
    _seed_iter_pre(d)

    def _fake_invoke(actuator: str, tool: str, args: dict) -> dict:
        if actuator == "oak-d" and args.get("query") == "red_blob":
            return {
                "telemetry": {
                    "found": True,
                    "centroid_px": [288, 410],
                    "centroid_depth_mm": 308,
                    "bbox_px": [275, 397, 301, 423],
                    "pixel_count": 312,
                    "provenance": {},
                }
            }
        if actuator == "oak-d" and args.get("query") == "bowl_top":
            return {
                "telemetry": {
                    "found": True,
                    "centroid_px": [285, 412],
                    "centroid_depth_mm": 305,
                    "bbox_px": [220, 350, 350, 470],
                    "pixel_count": 9412,
                    "provenance": {},
                }
            }
        if actuator == "so-arm101" and tool == "read_state":
            return {"telemetry": {"positions": {"gripper": 0.0}}}
        raise AssertionError(f"unexpected: {actuator}/{tool}/{args}")

    monkeypatch.setattr("robot_md.trial._gateway_invoke", _fake_invoke)

    result = CliRunner().invoke(
        trial_app, ["iteration", "--trial", d.name, "--capture-post-and-verdict"]
    )
    assert result.exit_code == 0, result.output

    iter1 = json.loads((d / "iter_1.json").read_text())
    verdict = iter1["verdict"]
    assert verdict["pass"] is True
    assert verdict["red_in_bowl"] is True
    assert verdict["depth_delta_mm"] == 3
    assert iter1["duration_s"] >= 0


def test_capture_post_fails_when_red_outside_bowl_bbox(trial_home, monkeypatch):
    from robot_md.trial import trial_app

    d = _seed_trial(trial_home)
    _seed_iter_pre(d)

    def _fake_invoke(actuator: str, tool: str, args: dict) -> dict:
        if actuator == "oak-d" and args.get("query") == "red_blob":
            return {
                "telemetry": {
                    "found": True,
                    "centroid_px": [50, 50],
                    "centroid_depth_mm": 308,
                    "bbox_px": [40, 40, 60, 60],
                    "pixel_count": 100,
                    "provenance": {},
                }
            }
        if actuator == "oak-d" and args.get("query") == "bowl_top":
            return {
                "telemetry": {
                    "found": True,
                    "centroid_px": [285, 412],
                    "centroid_depth_mm": 305,
                    "bbox_px": [220, 350, 350, 470],
                    "pixel_count": 9412,
                    "provenance": {},
                }
            }
        if actuator == "so-arm101" and tool == "read_state":
            return {"telemetry": {"positions": {}}}
        raise AssertionError(f"unexpected: {actuator}/{tool}/{args}")

    monkeypatch.setattr("robot_md.trial._gateway_invoke", _fake_invoke)

    result = CliRunner().invoke(
        trial_app, ["iteration", "--trial", d.name, "--capture-post-and-verdict"]
    )
    assert result.exit_code == 0, result.output

    iter1 = json.loads((d / "iter_1.json").read_text())
    verdict = iter1["verdict"]
    assert verdict["pass"] is False
    assert verdict["red_in_bowl"] is False


def test_capture_post_fails_when_depth_delta_over_80mm(trial_home, monkeypatch):
    from robot_md.trial import trial_app

    d = _seed_trial(trial_home)
    _seed_iter_pre(d)

    def _fake_invoke(actuator: str, tool: str, args: dict) -> dict:
        if actuator == "oak-d" and args.get("query") == "red_blob":
            return {
                "telemetry": {
                    "found": True,
                    "centroid_px": [288, 410],
                    "centroid_depth_mm": 200,
                    "bbox_px": [275, 397, 301, 423],
                    "pixel_count": 312,
                    "provenance": {},
                }
            }
        if actuator == "oak-d" and args.get("query") == "bowl_top":
            return {
                "telemetry": {
                    "found": True,
                    "centroid_px": [285, 412],
                    "centroid_depth_mm": 305,
                    "bbox_px": [220, 350, 350, 470],
                    "pixel_count": 9412,
                    "provenance": {},
                }
            }
        if actuator == "so-arm101" and tool == "read_state":
            return {"telemetry": {"positions": {"gripper": 0.0}}}
        raise AssertionError(f"unexpected: {actuator}/{tool}/{args}")

    monkeypatch.setattr("robot_md.trial._gateway_invoke", _fake_invoke)

    result = CliRunner().invoke(
        trial_app, ["iteration", "--trial", d.name, "--capture-post-and-verdict"]
    )
    assert result.exit_code == 0, result.output

    iter1 = json.loads((d / "iter_1.json").read_text())
    verdict = iter1["verdict"]
    assert verdict["pass"] is False
    assert verdict["depth_delta_mm"] == 105


def test_capture_post_fails_when_post_red_not_found(trial_home, monkeypatch):
    from robot_md.trial import trial_app

    d = _seed_trial(trial_home)
    _seed_iter_pre(d)

    def _fake_invoke(actuator: str, tool: str, args: dict) -> dict:
        if actuator == "oak-d" and args.get("query") == "red_blob":
            return {
                "telemetry": {
                    "found": False,
                    "pixel_count": 0,
                    "provenance": {},
                }
            }
        if actuator == "oak-d" and args.get("query") == "bowl_top":
            return {
                "telemetry": {
                    "found": True,
                    "centroid_px": [285, 412],
                    "centroid_depth_mm": 305,
                    "bbox_px": [220, 350, 350, 470],
                    "pixel_count": 9412,
                    "provenance": {},
                }
            }
        if actuator == "so-arm101" and tool == "read_state":
            return {"telemetry": {"positions": {"gripper": 0.0}}}
        raise AssertionError(f"unexpected: {actuator}/{tool}/{args}")

    monkeypatch.setattr("robot_md.trial._gateway_invoke", _fake_invoke)

    result = CliRunner().invoke(
        trial_app, ["iteration", "--trial", d.name, "--capture-post-and-verdict"]
    )
    assert result.exit_code == 0, result.output

    iter1 = json.loads((d / "iter_1.json").read_text())
    verdict = iter1["verdict"]
    assert verdict["pass"] is False
