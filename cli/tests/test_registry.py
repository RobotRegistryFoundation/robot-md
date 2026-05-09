"""Tests for robot_md.registry — fetch + scoring + formatting."""

from __future__ import annotations

import json

import pytest

from robot_md.registry import (
    DEFAULT_CATALOG_URL,
    extract_manifest_signals,
    fetch_index,
    format_search_results,
    score_entry,
)


def test_default_catalog_url_points_to_robotmd_dev():
    assert DEFAULT_CATALOG_URL == "https://robotmd.dev/actuators/index.json"


def test_fetch_index_writes_cache_on_success(tmp_path, monkeypatch):
    cache = tmp_path / "registry-index.json"
    payload = {"schema_version": "1.0", "entries": [{"type": "actuator", "name": "x"}]}

    class _FakeResp:
        def __init__(self, body):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=10):
        actual_url = req.full_url if hasattr(req, "full_url") else req
        assert actual_url == DEFAULT_CATALOG_URL
        if hasattr(req, "headers"):
            assert any(k.lower() == "user-agent" for k in req.headers)
        return _FakeResp(json.dumps(payload).encode())

    monkeypatch.setattr("robot_md.registry.urlopen", _fake_urlopen)
    out = fetch_index(cache_path=cache, offline=False)
    assert out == payload
    assert json.loads(cache.read_text()) == payload


def test_fetch_index_offline_reads_cache(tmp_path):
    cache = tmp_path / "registry-index.json"
    payload = {"schema_version": "1.0", "entries": []}
    cache.write_text(json.dumps(payload))
    out = fetch_index(cache_path=cache, offline=True)
    assert out == payload


def test_fetch_index_offline_missing_cache_raises(tmp_path):
    cache = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        fetch_index(cache_path=cache, offline=True)


def test_fetch_index_falls_back_to_cache_on_http_error(tmp_path, monkeypatch):
    cache = tmp_path / "registry-index.json"
    payload = {"schema_version": "1.0", "entries": [{"name": "stale"}]}
    cache.write_text(json.dumps(payload))

    def _fake_urlopen(req, timeout=10):
        raise OSError("network down")

    monkeypatch.setattr("robot_md.registry.urlopen", _fake_urlopen)
    out = fetch_index(cache_path=cache, offline=False)
    assert out == payload


def test_extract_manifest_signals_pulls_driver_ids_and_camera_ids():
    manifest = {
        "drivers": [
            {"id": "feetech_bus_0", "model": "SO-ARM101"},
            {"id": "oak_d_0", "model": "OAK-D-Lite"},
        ],
        "physics": {"solver": {"cameras": [{"driver_id": "oak_d_0"}]}},
    }
    sig = extract_manifest_signals(manifest)
    assert "feetech_bus_0" in sig
    assert "SO-ARM101" in sig
    assert "oak_d_0" in sig
    assert "OAK-D-Lite" in sig


def test_extract_manifest_signals_handles_missing_keys():
    assert extract_manifest_signals({}) == []
    assert extract_manifest_signals({"drivers": []}) == []
    assert extract_manifest_signals({"physics": {}}) == []


def test_score_entry_high_when_manifest_signal_overlaps():
    entry = {
        "name": "x",
        "description": "irrelevant",
        "hardware_tags": [],
        "manifest_signals": ["SO-ARM101"],
    }
    score = score_entry(entry, query="", manifest_signals=["SO-ARM101", "OAK-D-Lite"])
    assert score >= 0.55  # at least the 0.6 weight from signal overlap


def test_score_entry_zero_when_no_overlap():
    entry = {
        "name": "x",
        "description": "robot arm driver",
        "hardware_tags": ["arm"],
        "manifest_signals": ["unobtanium"],
    }
    score = score_entry(entry, query="aquarium pump", manifest_signals=[])
    assert score == 0.0


def test_score_entry_renormalizes_when_no_manifest():
    entry = {
        "name": "x",
        "description": "raspberry pi camera driver",
        "hardware_tags": ["raspberry-pi", "camera"],
        "manifest_signals": [],
    }
    score = score_entry(entry, query="raspberry pi", manifest_signals=None)
    # 0.3 (tag) + 0.1 (desc fuzzy) = 0.4 in raw weights; renormalized = 1.0.
    assert score == pytest.approx(1.0, abs=0.01)


def test_format_search_results_empty_says_no_match():
    out = format_search_results([], threshold=0.3)
    assert "No matches found" in out
    assert "robot-md actuator publish" in out


def test_format_search_results_lists_top_entries_with_score():
    scored = [
        (
            {
                "name": "match-a",
                "version": "1.0",
                "description": "desc-a",
                "install": {"package_manager": "pip", "package": "match-a"},
            },
            0.95,
        ),
        (
            {
                "name": "match-b",
                "version": "0.2",
                "description": "desc-b",
                "install": {"package_manager": "pip", "package": "match-b"},
                "plugin_marketplace_entry": {"install_command": "/plugin install match-b@rrf"},
            },
            0.5,
        ),
    ]
    out = format_search_results(scored, threshold=0.3)
    assert "match-a" in out and "0.95" in out
    assert "match-b" in out and "0.50" in out
    # Plugin entry preferred over pip when both present.
    assert "/plugin install match-b@rrf" in out
    assert "pip install match-a" in out


def test_format_search_results_marks_below_threshold_as_weak():
    scored = [
        (
            {
                "name": "weak",
                "version": "0.1",
                "description": "barely",
                "install": {"package_manager": "pip", "package": "weak"},
            },
            0.15,
        ),
    ]
    out = format_search_results(scored, threshold=0.3)
    assert "weak match" in out
    assert "weak" in out  # entry still printed, not filtered out
