from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture
def dashboard_app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".robot-md").mkdir()
    from robot_md.dashboard.server import build_app

    app = build_app(manifest=None)
    return app, tmp_path


def test_dashboard_renders_index(dashboard_app):
    app, _ = dashboard_app
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        # "robot-md" should appear as the default robot name in header
        assert "robot-md" in r.text.lower()


def test_dashboard_estop_button_writes_command(dashboard_app):
    app, tmp_path = dashboard_app
    with TestClient(app) as client:
        r = client.post("/api/estop")
        assert r.status_code == 200
    cmd_path = tmp_path / ".robot-md" / "commands.jsonl"
    assert cmd_path.exists()
    lines = cmd_path.read_text().splitlines()
    assert any(json.loads(line).get("cmd") == "estop.set" for line in lines)


def test_dashboard_estop_clear_button_writes_command(dashboard_app):
    app, tmp_path = dashboard_app
    with TestClient(app) as client:
        r = client.post("/api/estop/clear")
        assert r.status_code == 200
    cmd_path = tmp_path / ".robot-md" / "commands.jsonl"
    lines = cmd_path.read_text().splitlines()
    assert any(json.loads(line).get("cmd") == "estop.clear" for line in lines)


def test_dashboard_snapshot_button_writes_command(dashboard_app):
    app, tmp_path = dashboard_app
    with TestClient(app) as client:
        r = client.post("/api/snapshot")
        assert r.status_code == 200
    cmd_path = tmp_path / ".robot-md" / "commands.jsonl"
    lines = cmd_path.read_text().splitlines()
    assert any(json.loads(line).get("cmd") == "snapshot" for line in lines)


def test_dashboard_frame_returns_404_when_none(dashboard_app):
    app, _ = dashboard_app
    with TestClient(app) as client:
        r = client.get("/api/frame/latest.png")
        assert r.status_code == 404


def test_dashboard_tunnel_returns_empty_when_absent(dashboard_app):
    app, _ = dashboard_app
    with TestClient(app) as client:
        r = client.get("/api/tunnel")
        assert r.status_code == 200
        assert r.json() == {}


def test_dashboard_tunnel_returns_json_when_present(dashboard_app):
    app, tmp_path = dashboard_app
    tunnel_json = tmp_path / ".robot-md" / "tunnel.json"
    tunnel_json.write_text(
        '{"url": "https://abc.trycloudflare.com", "alive": true, "since": 123.4}'
    )
    with TestClient(app) as client:
        r = client.get("/api/tunnel")
        assert r.status_code == 200
        body = r.json()
        assert body["url"] == "https://abc.trycloudflare.com"
        assert body["alive"] is True


def test_dashboard_tunnel_returns_empty_on_malformed_json(dashboard_app):
    app, tmp_path = dashboard_app
    tunnel_json = tmp_path / ".robot-md" / "tunnel.json"
    tunnel_json.write_text("not valid json {")
    with TestClient(app) as client:
        r = client.get("/api/tunnel")
        assert r.status_code == 200
        assert r.json() == {}
