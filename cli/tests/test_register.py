"""Tests for `robot-md register` — signed POST + manifest rewrite (v0.9.1).

The live RRF endpoint is exercised via mocked urlopen; real hits against
https://robotregistryfoundation.org would pollute the public registry.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("ruamel.yaml")

from robot_md.register import (
    DEFAULT_ENDPOINT,
    MintRequest,
    _extract_mint_fields,
    cli_register,
    post_to_rrf,
)
from robot_md.signing import verify_body

BOB_MIN = """\
---
rcan_version: "3.0"
metadata:
  robot_name: bob
  manufacturer: craigm26
  model: opencastor-rpi5-hailo
  firmware_version: 1.0.0
physics:
  type: arm
  dof: 6
drivers:
  - { id: arm, protocol: feetech, port: /dev/ttyACM0 }
safety:
  estop: { software: true, response_ms: 100 }
---
# bob
Test.
"""


def _write(tmp_path: Path, content: str = BOB_MIN) -> Path:
    p = tmp_path / "bob.ROBOT.md"
    p.write_text(content)
    return p


# ---- _extract_mint_fields (current API) ---------------------------------


def test_extract_from_manifest(tmp_path):
    path = _write(tmp_path)
    req = _extract_mint_fields(
        path,
        name=None, manufacturer=None, model=None,
        firmware_version=None, rcan_version=None, pq_signing_pub=None,
    )
    assert req.name == "bob"
    assert req.manufacturer == "craigm26"
    assert req.model == "opencastor-rpi5-hailo"
    assert req.firmware_version == "1.0.0"
    assert req.rcan_version == "3.0"


def test_cli_overrides_win(tmp_path):
    path = _write(tmp_path)
    req = _extract_mint_fields(
        path,
        name="override-bot", manufacturer="acme", model="rx-1",
        firmware_version="2.0.0", rcan_version="3.0", pq_signing_pub=None,
    )
    assert req.name == "override-bot"
    assert req.manufacturer == "acme"
    assert req.model == "rx-1"


def test_missing_robot_name_raises(tmp_path):
    bad = BOB_MIN.replace("robot_name: bob", "robot_name: ")
    path = _write(tmp_path, bad)
    with pytest.raises(ValueError, match="robot_name"):
        _extract_mint_fields(path, name=None, manufacturer=None, model=None,
                             firmware_version=None, rcan_version=None, pq_signing_pub=None)


# ---- MintRequest shape --------------------------------------------------


def test_mint_request_as_body_strips_empty_optionals():
    req = MintRequest(
        name="x", manufacturer="y", model="z",
        firmware_version="1.0", rcan_version="3.0",
    )
    body = req.as_body()
    assert body == {
        "name": "x", "manufacturer": "y", "model": "z",
        "firmware_version": "1.0", "rcan_version": "3.0",
    }
    assert "pq_signing_pub" not in body


def test_mint_request_as_body_includes_set_optionals():
    req = MintRequest(
        name="x", manufacturer="y", model="z",
        firmware_version="1.0", rcan_version="3.0",
        pq_signing_pub="pubkey", pq_kid="abcd1234",
        ruri="rcan://example/y/z/x",
    )
    body = req.as_body()
    assert body["pq_signing_pub"] == "pubkey"
    assert body["pq_kid"] == "abcd1234"
    assert body["ruri"] == "rcan://example/y/z/x"


# ---- signed register flow (v0.9.1) --------------------------------------


def test_cli_register_signs_body_before_posting(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = _write(tmp_path)

    captured = {}
    def fake_post(endpoint, body, timeout=15.0):
        captured["body"] = body
        from robot_md.register import MintResult
        return MintResult(
            rrn="RRN-000000000099",
            registered_at="2026-04-22T12:00:00Z",
            record_url="https://robotregistryfoundation.org/v2/robots/RRN-000000000099",
            raw={"rrn": "RRN-000000000099", "api_key": "secret-xyz"},
        )

    with patch("robot_md.register.post_to_rrf", fake_post):
        rc = cli_register(path, endpoint=DEFAULT_ENDPOINT)
    assert rc == 0

    body = captured["body"]
    assert "pq_signing_pub" in body
    assert "pq_kid" in body
    assert "sig" in body
    assert set(body["sig"].keys()) == {"ml_dsa", "ed25519", "ed25519_pub"}
    # Verify the body self-signs correctly
    assert verify_body(body) is True


def test_cli_register_constructs_ruri_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = _write(tmp_path)

    captured = {}
    def fake_post(endpoint, body, timeout=15.0):
        captured["body"] = body
        from robot_md.register import MintResult
        return MintResult(rrn="RRN-000000000099", registered_at="x",
                          record_url="u", raw={"api_key": "k"})

    with patch("robot_md.register.post_to_rrf", fake_post):
        cli_register(path, endpoint=DEFAULT_ENDPOINT)

    assert captured["body"]["ruri"] == (
        "rcan://robotregistryfoundation.org/craigm26/opencastor-rpi5-hailo/bob"
    )


def test_cli_register_saves_keypair_after_success(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = _write(tmp_path)

    def fake_post(endpoint, body, timeout=15.0):
        from robot_md.register import MintResult
        return MintResult(rrn="RRN-000000000099", registered_at="x",
                          record_url="u", raw={"api_key": "k"})

    with patch("robot_md.register.post_to_rrf", fake_post):
        cli_register(path, endpoint=DEFAULT_ENDPOINT)

    key_path = tmp_path / ".robot-md" / "keys" / "RRN-000000000099.signing.json"
    assert key_path.exists()
    apikey_path = tmp_path / ".robot-md" / "keys" / "RRN-000000000099.apikey"
    assert apikey_path.exists()


def test_cli_register_already_registered_raises(tmp_path, monkeypatch):
    """Running register on a manifest that already has metadata.rrn is an error
    in v0.9.1 — rotation is a later release."""
    monkeypatch.setenv("HOME", str(tmp_path))
    content = BOB_MIN.replace(
        "robot_name: bob",
        "robot_name: bob\n  rrn: RRN-000000000099",
    )
    path = _write(tmp_path, content)
    rc = cli_register(path, endpoint=DEFAULT_ENDPOINT)
    assert rc != 0


# ---- post_to_rrf network-layer tests -----------------------------------


def test_post_to_rrf_success_parses_mint_result(monkeypatch):
    response = MagicMock()
    response.read.return_value = json.dumps({
        "rrn": "RRN-000000000099",
        "registered_at": "2026-04-22T12:00:00Z",
        "record_url": "https://robotregistryfoundation.org/v2/robots/RRN-000000000099",
        "api_key": "secret-xyz",
    }).encode()
    response.status = 201
    response.__enter__ = lambda s: s
    response.__exit__ = lambda *a: None

    with patch("urllib.request.urlopen", return_value=response):
        result = post_to_rrf(DEFAULT_ENDPOINT, {"name": "x"})
    assert result.rrn == "RRN-000000000099"
    assert result.record_url.endswith("/RRN-000000000099")
    assert result.raw["api_key"] == "secret-xyz"
