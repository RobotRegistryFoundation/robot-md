"""Tests for RRF packages HTTP client."""

from __future__ import annotations

import pytest

from robot_md.rrf_packages import (
    RRF_PACKAGES_BASE,
    PackageConflictError,
    PackageNotFoundError,
    SignatureError,
    append_version,
    fetch_one,
    list_packages,
    register_package,
    revoke_package,
    transfer_package,
)


class _FakeResp:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_default_url_points_to_rrf_org():
    assert RRF_PACKAGES_BASE == "https://robotregistryfoundation.org/v2/packages"


def test_register_package_returns_rpn(monkeypatch):
    captured = {}

    def _fake_urlopen(req, timeout=10):
        captured["url"] = req.full_url
        captured["body"] = req.data
        return _FakeResp(
            201,
            b'{"rpn":"RPN-000000000001","registered_at":"2026-05-09T00:00:00Z","record_url":"x"}',
        )

    monkeypatch.setattr("robot_md.rrf_packages.urlopen", _fake_urlopen)
    out = register_package(signed_body={"name": "x"})
    assert out["rpn"] == "RPN-000000000001"
    assert captured["url"].endswith("/v2/packages/register")
    assert b'"name"' in captured["body"]


def test_fetch_one_returns_record(monkeypatch):
    def _fake(req, timeout=10):
        return _FakeResp(200, b'{"rpn":"RPN-000000000001","name":"x"}')

    monkeypatch.setattr("robot_md.rrf_packages.urlopen", _fake)
    rec = fetch_one("RPN-000000000001")
    assert rec["rpn"] == "RPN-000000000001"


def test_fetch_one_raises_on_404(monkeypatch):
    from urllib.error import HTTPError

    def _fake(req, timeout=10):
        raise HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr("robot_md.rrf_packages.urlopen", _fake)
    with pytest.raises(PackageNotFoundError):
        fetch_one("RPN-000000000099")


def test_list_packages_passes_filters(monkeypatch):
    captured = {}

    def _fake(req, timeout=10):
        captured["url"] = req.full_url
        return _FakeResp(200, b'{"packages":[]}')

    monkeypatch.setattr("robot_md.rrf_packages.urlopen", _fake)
    list_packages(type_filter="actuator", tag="arm", include_revoked=True)
    assert "type=actuator" in captured["url"]
    assert "tag=arm" in captured["url"]
    assert "include_revoked=1" in captured["url"]


def test_register_raises_on_conflict(monkeypatch):
    from urllib.error import HTTPError

    def _fake(req, timeout=10):
        raise HTTPError(req.full_url, 409, "Conflict", {}, None)

    monkeypatch.setattr("robot_md.rrf_packages.urlopen", _fake)
    with pytest.raises(PackageConflictError):
        register_package(signed_body={"name": "x"})


def test_register_raises_on_signature_failure(monkeypatch):
    from urllib.error import HTTPError

    def _fake(req, timeout=10):
        raise HTTPError(req.full_url, 400, "Bad", {}, None)

    monkeypatch.setattr("robot_md.rrf_packages.urlopen", _fake)
    with pytest.raises(SignatureError):
        register_package(signed_body={"name": "x"})


def test_append_version_calls_correct_url(monkeypatch):
    captured = {}

    def _fake(req, timeout=10):
        captured["url"] = req.full_url
        return _FakeResp(200, b'{"rpn":"RPN-000000000001","versions":[]}')

    monkeypatch.setattr("robot_md.rrf_packages.urlopen", _fake)
    append_version("RPN-000000000001", signed_body={"version": "1.1.0"})
    assert captured["url"].endswith("/v2/packages/RPN-000000000001/versions")


def test_revoke_package_calls_correct_url(monkeypatch):
    captured = {}

    def _fake(req, timeout=10):
        captured["url"] = req.full_url
        return _FakeResp(200, b"{}")

    monkeypatch.setattr("robot_md.rrf_packages.urlopen", _fake)
    revoke_package("RPN-000000000001", signed_body={"reason": "x"})
    assert captured["url"].endswith("/v2/packages/RPN-000000000001/revoke")


def test_transfer_package_calls_correct_url(monkeypatch):
    captured = {}

    def _fake(req, timeout=10):
        captured["url"] = req.full_url
        return _FakeResp(200, b"{}")

    monkeypatch.setattr("robot_md.rrf_packages.urlopen", _fake)
    transfer_package("RPN-000000000001", signed_body={"new_pq_signing_pub": "x"})
    assert captured["url"].endswith("/v2/packages/RPN-000000000001/transfer")


def test_user_agent_header_set(monkeypatch):
    captured = {}

    def _fake(req, timeout=10):
        captured["ua"] = req.get_header("User-agent")
        return _FakeResp(200, b'{"packages":[]}')

    monkeypatch.setattr("robot_md.rrf_packages.urlopen", _fake)
    list_packages(type_filter="actuator")
    assert captured["ua"] is not None
    assert "robot-md" in captured["ua"]
