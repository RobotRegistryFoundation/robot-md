"""Tests for robot_md.registry — fetch + scoring + formatting."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from robot_md.registry import (
    DEFAULT_CATALOG_URL,
    fetch_index,
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

    def _fake_urlopen(url, timeout=10):
        assert url == DEFAULT_CATALOG_URL
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

    def _fake_urlopen(url, timeout=10):
        raise OSError("network down")

    monkeypatch.setattr("robot_md.registry.urlopen", _fake_urlopen)
    out = fetch_index(cache_path=cache, offline=False)
    assert out == payload
