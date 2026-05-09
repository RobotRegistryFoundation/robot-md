"""Tests for `robot-md actuator revoke` and `robot-md actuator transfer`."""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from robot_md.__main__ import app

runner = CliRunner()


class _DummyKp:
    pq_kid = "publisher-alice"
    pq_signing_pub = b"PUB"
    pq_signing_sec = b"SEC"
    ed25519_pub = b"EPUB"
    ed25519_sec = b"ESEC"


def _record_rpn(monkeypatch, tmp_path, package_name: str, rpn: str):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = tmp_path / ".robot-md" / "published" / f"{package_name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"rpn": rpn, "record_url": "x"}))


def test_revoke_calls_rrf(monkeypatch, tmp_path):
    captured = {}

    def _fake(rpn, *, signed_body, timeout=10.0):
        captured["rpn"] = rpn
        captured["body"] = signed_body
        return {"rpn": rpn, "status": "revoked"}

    monkeypatch.setattr("robot_md.actuator.revoke_package", _fake)
    monkeypatch.setattr("robot_md.actuator.load_or_mint_publisher_key", lambda u: _DummyKp())
    monkeypatch.setattr(
        "robot_md.actuator._sign",
        lambda fields, kp: {**fields, "sig": {"ml_dsa": "FAKE", "ed25519": "FAKE"}},
    )
    res = runner.invoke(
        app,
        ["actuator", "revoke", "RPN-000000000007", "--reason", "abandoned",
         "--github-user", "alice"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code == 0, res.output
    assert captured["rpn"] == "RPN-000000000007"
    assert captured["body"]["reason"] == "abandoned"
    assert "sig" in captured["body"]


def test_revoke_rejects_malformed_rpn(monkeypatch, tmp_path):
    monkeypatch.setattr("robot_md.actuator.load_or_mint_publisher_key", lambda u: _DummyKp())
    res = runner.invoke(
        app,
        ["actuator", "revoke", "garbage", "--reason", "test", "--github-user", "alice"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code != 0
    assert "RPN" in res.output or "malformed" in res.output.lower()


def test_revoke_requires_reason(monkeypatch, tmp_path):
    res = runner.invoke(
        app,
        ["actuator", "revoke", "RPN-000000000007", "--github-user", "alice"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code != 0
    assert "reason" in res.output.lower()


def test_transfer_calls_rrf_with_new_keys(monkeypatch, tmp_path):
    captured = {}

    def _fake(rpn, *, signed_body, timeout=10.0):
        captured["rpn"] = rpn
        captured["body"] = signed_body
        return {"rpn": rpn}

    monkeypatch.setattr("robot_md.actuator.transfer_package", _fake)
    monkeypatch.setattr("robot_md.actuator.load_or_mint_publisher_key", lambda u: _DummyKp())
    monkeypatch.setattr(
        "robot_md.actuator._sign",
        lambda fields, kp: {**fields, "sig": {"ml_dsa": "FAKE", "ed25519": "FAKE"}},
    )
    monkeypatch.setattr(
        "robot_md.actuator._read_pub_keys_from_pem",
        lambda p: ("NEW_PQ_PUB", "publisher-bob", "NEW_ED_PUB"),
    )
    res = runner.invoke(
        app,
        ["actuator", "transfer", "RPN-000000000007", "--to-key", "/tmp/new-pub.pem",
         "--github-user", "alice"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code == 0, res.output
    assert captured["rpn"] == "RPN-000000000007"
    assert captured["body"]["new_pq_signing_pub"] == "NEW_PQ_PUB"
    assert captured["body"]["new_pq_kid"] == "publisher-bob"
    assert captured["body"]["new_ed25519_pub"] == "NEW_ED_PUB"
    assert "sig" in captured["body"]


def test_transfer_rejects_missing_to_key(monkeypatch, tmp_path):
    res = runner.invoke(
        app,
        ["actuator", "transfer", "RPN-000000000007", "--github-user", "alice"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code != 0


def test_revoke_propagates_rrf_404(monkeypatch, tmp_path):
    from robot_md.rrf_packages import PackageNotFoundError

    def _fake(*a, **kw):
        raise PackageNotFoundError("not found")

    monkeypatch.setattr("robot_md.actuator.revoke_package", _fake)
    monkeypatch.setattr("robot_md.actuator.load_or_mint_publisher_key", lambda u: _DummyKp())
    monkeypatch.setattr(
        "robot_md.actuator._sign",
        lambda fields, kp: {**fields, "sig": {"ml_dsa": "FAKE", "ed25519": "FAKE"}},
    )
    res = runner.invoke(
        app,
        ["actuator", "revoke", "RPN-000000000099", "--reason", "x", "--github-user", "alice"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code != 0
    assert "not found" in res.output.lower() or "404" in res.output.lower() or "no package" in res.output.lower()
