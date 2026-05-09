"""Tests for robot_md.actuator.actuator_search business logic."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from robot_md.__main__ import app
from robot_md.actuator import RPN_PATTERN, actuator_search, actuator_search_by_rpn

runner = CliRunner()


def _fake_index() -> dict:
    return {
        "schema_version": "1.0",
        "entries": [
            {
                "type": "actuator",
                "name": "feetech-arm",
                "version": "1.0",
                "description": "Feetech bus arm driver",
                "hardware_tags": ["arm", "feetech"],
                "manifest_signals": ["SO-ARM101"],
                "install": {"package_manager": "pip", "package": "feetech-arm"},
            },
            {
                "type": "actuator",
                "name": "rpi-camera",
                "version": "0.3",
                "description": "Raspberry Pi camera driver",
                "hardware_tags": ["raspberry-pi", "camera"],
                "manifest_signals": [],
                "install": {"package_manager": "pip", "package": "rpi-camera"},
            },
            {
                "type": "skill",
                "name": "skill-x",
                "description": "a skill, not an actuator",
                "hardware_tags": [],
                "install": {"package_manager": "pip", "package": "skill-x"},
            },
        ],
    }


def test_actuator_search_filters_to_actuator_type_by_default():
    out = actuator_search(_fake_index(), query="raspberry pi", manifest=None)
    assert "rpi-camera" in out
    assert "skill-x" not in out  # type=skill filtered out


def test_actuator_search_with_manifest_uses_signals():
    manifest = {"drivers": [{"id": "feetech_bus_0", "model": "SO-ARM101"}]}
    out = actuator_search(_fake_index(), query="", manifest=manifest)
    assert "feetech-arm" in out


def test_actuator_search_no_results_prints_no_matches():
    out = actuator_search(_fake_index(), query="aquarium", manifest=None)
    assert "No matches found" in out


def test_actuator_search_type_override_searches_all():
    out = actuator_search(_fake_index(), query="skill", manifest=None, type_filter="skill")
    assert "skill-x" in out


def test_actuator_search_threshold_marks_weak():
    # Query has no token overlap and no manifest, so all scores are 0 → weak.
    idx = _fake_index()
    out = actuator_search(idx, query="z" * 30, manifest=None, threshold=0.3)
    # All filtered out (score 0.0 < 0.3 means weak — but format_search_results
    # only prints up to limit anyway). Check the no-match path triggers when
    # nothing scores above 0.
    assert "No matches" in out or "weak match" in out


def test_search_subcommand_help_is_listed():
    res = runner.invoke(
        app, ["actuator", "--help"], env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"}
    )
    assert res.exit_code == 0
    assert "search" in res.stdout


def test_search_offline_uses_cache(tmp_path, monkeypatch):
    cache = tmp_path / "registry-index.json"
    cache.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "entries": [
                    {
                        "type": "actuator",
                        "name": "cached-act",
                        "version": "1",
                        "description": "cached entry",
                        "hardware_tags": ["test"],
                        "manifest_signals": [],
                        "install": {"package_manager": "pip", "package": "cached-act"},
                    }
                ],
            }
        )
    )
    monkeypatch.setattr("robot_md.registry.DEFAULT_CACHE_PATH", cache)
    res = runner.invoke(
        app,
        ["actuator", "search", "test", "--offline"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code == 0, res.output
    assert "cached-act" in res.stdout


def test_rpn_pattern_matches_well_formed():
    assert RPN_PATTERN.match("RPN-000000000001")
    assert not RPN_PATTERN.match("RPN-1")
    assert not RPN_PATTERN.match("RRN-000000000001")


def test_actuator_search_by_rpn_calls_fetch_one(monkeypatch):
    captured = {}

    def _fake(rpn, **kw):
        captured["rpn"] = rpn
        return {
            "rpn": rpn,
            "name": "found",
            "version": "1.0",
            "description": "x",
            "hardware_tags": [],
            "install": {"package_manager": "pip", "package": "found"},
        }

    monkeypatch.setattr("robot_md.actuator.fetch_one", _fake)
    out = actuator_search_by_rpn("RPN-000000000001")
    assert "found" in out
    assert "RPN-000000000001" in out
    assert captured["rpn"] == "RPN-000000000001"


def test_search_command_dispatches_to_rpn_lookup(monkeypatch):
    def _fake(rpn, **kw):
        return {
            "rpn": rpn,
            "name": "looked-up",
            "version": "1.0",
            "description": "via direct lookup",
            "hardware_tags": [],
            "install": {"package_manager": "pip", "package": "x"},
        }

    monkeypatch.setattr("robot_md.actuator.fetch_one", _fake)
    res = runner.invoke(
        app,
        ["actuator", "search", "RPN-000000000001"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code == 0, res.output
    assert "looked-up" in res.stdout
    assert "RPN-000000000001" in res.stdout
