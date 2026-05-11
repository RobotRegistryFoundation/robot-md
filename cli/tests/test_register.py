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
    peek_next_rrn,
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
        name=None,
        manufacturer=None,
        model=None,
        firmware_version=None,
        rcan_version=None,
        pq_signing_pub=None,
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
        name="override-bot",
        manufacturer="acme",
        model="rx-1",
        firmware_version="2.0.0",
        rcan_version="3.0",
        pq_signing_pub=None,
    )
    assert req.name == "override-bot"
    assert req.manufacturer == "acme"
    assert req.model == "rx-1"


def test_missing_robot_name_raises(tmp_path):
    bad = BOB_MIN.replace("robot_name: bob", "robot_name: ")
    path = _write(tmp_path, bad)
    with pytest.raises(ValueError, match="robot_name"):
        _extract_mint_fields(
            path,
            name=None,
            manufacturer=None,
            model=None,
            firmware_version=None,
            rcan_version=None,
            pq_signing_pub=None,
        )


# ---- MintRequest shape --------------------------------------------------


def test_mint_request_as_body_strips_empty_optionals():
    req = MintRequest(
        name="x",
        manufacturer="y",
        model="z",
        firmware_version="1.0",
        rcan_version="3.0",
    )
    body = req.as_body()
    assert body == {
        "name": "x",
        "manufacturer": "y",
        "model": "z",
        "firmware_version": "1.0",
        "rcan_version": "3.0",
    }
    assert "pq_signing_pub" not in body


def test_mint_request_as_body_includes_set_optionals():
    req = MintRequest(
        name="x",
        manufacturer="y",
        model="z",
        firmware_version="1.0",
        rcan_version="3.0",
        pq_signing_pub="pubkey",
        pq_kid="abcd1234",
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

        return MintResult(
            rrn="RRN-000000000099", registered_at="x", record_url="u", raw={"api_key": "k"}
        )

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

        return MintResult(
            rrn="RRN-000000000099", registered_at="x", record_url="u", raw={"api_key": "k"}
        )

    with patch("robot_md.register.post_to_rrf", fake_post):
        cli_register(path, endpoint=DEFAULT_ENDPOINT)

    key_path = tmp_path / ".robot-md" / "keys" / "RRN-000000000099.signing.json"
    assert key_path.exists()
    apikey_path = tmp_path / ".robot-md" / "keys" / "RRN-000000000099.apikey"
    assert apikey_path.exists()


# ---- envelope-authority auto-registration (closes #84) ------------------


def test_cli_register_publishes_envelope_authority_after_mint(tmp_path, monkeypatch):
    """After a successful robot mint, register also POSTs to
    /v2/authorities/register so the robot's pq_kid resolves at /v2/keys/{kid}.
    Without this step gateway envelope auth 403s on first invoke."""
    monkeypatch.setenv("HOME", str(tmp_path))
    path = _write(tmp_path)

    captured: dict[str, dict] = {}

    def fake_post(endpoint, body, timeout=15.0):
        from robot_md.register import MintResult

        captured["mint"] = body
        return MintResult(
            rrn="RRN-000000000099",
            registered_at="2026-05-11T21:00:00Z",
            record_url="https://robotregistryfoundation.org/v2/robots/RRN-000000000099",
            raw={"rrn": "RRN-000000000099", "api_key": "secret-xyz"},
        )

    def fake_authority_post(endpoint, body, timeout=15.0):
        captured["authority_endpoint"] = endpoint
        captured["authority"] = body
        return {
            "ran": "RAN-000000000042",
            "status": "active",
            "registered_at": "2026-05-11T21:00:01Z",
        }

    with (
        patch("robot_md.register.post_to_rrf", fake_post),
        patch("robot_md.register.post_envelope_authority", fake_authority_post),
    ):
        rc = cli_register(path, endpoint=DEFAULT_ENDPOINT)

    assert rc == 0
    # The authority POST went to the authorities/register endpoint
    assert captured["authority_endpoint"].endswith("/v2/authorities/register")
    auth = captured["authority"]
    # All 8 required fields per RRF functions/v2/authorities/register.ts
    for key in (
        "organization",
        "display_name",
        "purpose",
        "signing_pub",
        "pq_signing_pub",
        "pq_kid",
        "signing_alg",
        "sig",
    ):
        assert key in auth, f"missing required field: {key}"
    assert auth["purpose"] == "operator-envelope"
    assert auth["signing_alg"] == ["Ed25519", "ML-DSA-65"]
    # sig.ed25519_pub must equal signing_pub (RRF rejects otherwise)
    assert auth["sig"]["ed25519_pub"] == auth["signing_pub"]
    assert set(auth["sig"].keys()) == {"ml_dsa", "ed25519", "ed25519_pub"}
    # pq_kid in the authority body matches the one minted on the robot record
    assert auth["pq_kid"] == captured["mint"]["pq_kid"]
    # Body self-verifies via the same primitive RRF uses (rcan-ts verifyBody)
    assert verify_body(auth) is True


def test_cli_register_succeeds_when_envelope_authority_post_fails(tmp_path, monkeypatch, capsys):
    """If the authority POST fails (network error, RRF down, etc.), register
    must still return 0 — the manifest already has a valid RRN. A warning is
    printed; operator can re-publish via a later command."""
    monkeypatch.setenv("HOME", str(tmp_path))
    path = _write(tmp_path)

    def fake_post(endpoint, body, timeout=15.0):
        from robot_md.register import MintResult

        return MintResult(
            rrn="RRN-000000000099", registered_at="x", record_url="u", raw={"api_key": "k"}
        )

    def fake_authority_post_fails(endpoint, body, timeout=15.0):
        raise RuntimeError("authorities/register returned 503: backend unavailable")

    with (
        patch("robot_md.register.post_to_rrf", fake_post),
        patch("robot_md.register.post_envelope_authority", fake_authority_post_fails),
    ):
        rc = cli_register(path, endpoint=DEFAULT_ENDPOINT)

    assert rc == 0
    err = capsys.readouterr().err
    assert "envelope" in err.lower() or "authority" in err.lower()


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
    response.read.return_value = json.dumps(
        {
            "rrn": "RRN-000000000099",
            "registered_at": "2026-04-22T12:00:00Z",
            "record_url": "https://robotregistryfoundation.org/v2/robots/RRN-000000000099",
            "api_key": "secret-xyz",
        }
    ).encode()
    response.status = 201
    response.__enter__ = lambda s: s
    response.__exit__ = lambda *a: None

    with patch("urllib.request.urlopen", return_value=response):
        result = post_to_rrf(DEFAULT_ENDPOINT, {"name": "x"})
    assert result.rrn == "RRN-000000000099"
    assert result.record_url.endswith("/RRN-000000000099")
    assert result.raw["api_key"] == "secret-xyz"


# ---- auto_mint_if_needed (v0.9.1 PATCH flow) ---------------------------


def test_auto_mint_noop_when_keystore_has_signing_key(tmp_path, monkeypatch):
    from robot_md.register import auto_mint_if_needed
    from robot_md.signing import generate_keypair, save_keypair

    monkeypatch.setenv("HOME", str(tmp_path))
    save_keypair("RRN-000000000099", generate_keypair())

    with patch("robot_md.register.patch_rrf") as p:
        auto_mint_if_needed("RRN-000000000099", endpoint=DEFAULT_ENDPOINT)
        assert not p.called  # early-return: no PATCH


def test_auto_mint_patches_rrf_when_signing_key_missing(tmp_path, monkeypatch):
    from robot_md.register import auto_mint_if_needed
    from robot_md.signing import load_keypair

    monkeypatch.setenv("HOME", str(tmp_path))
    # Pretend the robot has an apikey but no signing key
    (tmp_path / ".robot-md" / "keys").mkdir(parents=True)
    (tmp_path / ".robot-md" / "keys" / "RRN-000000000099.apikey").write_text("secret-xyz")

    captured = {}

    def fake_patch(url, body, api_key, timeout=15.0):
        captured["url"] = url
        captured["body"] = body
        captured["api_key"] = api_key
        return {
            "rrn": "RRN-000000000099",
            "pq_signing_pub": body["pq_signing_pub"],
            "pq_kid": body["pq_kid"],
        }

    with patch("robot_md.register.patch_rrf", fake_patch):
        auto_mint_if_needed("RRN-000000000099", endpoint=DEFAULT_ENDPOINT)

    assert captured["url"].endswith("/RRN-000000000099")
    assert captured["api_key"] == "secret-xyz"
    assert "pq_signing_pub" in captured["body"]
    assert "sig" in captured["body"]
    # Keypair was saved
    assert load_keypair("RRN-000000000099") is not None


def test_auto_mint_skips_when_no_apikey(tmp_path, monkeypatch):
    """If the user doesn't have an apikey for the RRN, auto-mint can't PATCH.
    This is not an error — just a no-op; the command that called auto_mint
    will surface its own error if it needs the apikey."""
    from robot_md.register import auto_mint_if_needed

    monkeypatch.setenv("HOME", str(tmp_path))
    with patch("robot_md.register.patch_rrf") as p:
        auto_mint_if_needed("RRN-000000000099", endpoint=DEFAULT_ENDPOINT)
        assert not p.called


# ---- v0.9.7 sibling §21 IDs passthrough --------------------------------


def test_mint_request_as_body_includes_sibling_ids():
    req = MintRequest(
        name="x",
        manufacturer="y",
        model="z",
        firmware_version="1.0",
        rcan_version="3.0",
        rcn_ids=("RCN-000000000001", "RCN-000000000002"),
        rmn="RMN-000000000007",
        rhn_ids=("RHN-000000000099",),
    )
    body = req.as_body()
    assert body["rcn_ids"] == ["RCN-000000000001", "RCN-000000000002"]
    assert body["rmn"] == "RMN-000000000007"
    assert body["rhn_ids"] == ["RHN-000000000099"]


def test_mint_request_as_body_strips_empty_sibling_ids():
    req = MintRequest(
        name="x",
        manufacturer="y",
        model="z",
        firmware_version="1.0",
        rcan_version="3.0",
    )
    body = req.as_body()
    assert "rcn_ids" not in body
    assert "rmn" not in body
    assert "rhn_ids" not in body


def test_extract_mint_fields_pulls_sibling_ids_from_manifest(tmp_path):
    manifest = BOB_MIN.replace(
        "  firmware_version: 1.0.0\n",
        "  firmware_version: 1.0.0\n"
        "  rcn_ids:\n    - RCN-000000000001\n    - RCN-000000000002\n"
        "  rmn: RMN-000000000007\n"
        "  rhn_ids:\n    - RHN-000000000099\n",
    )
    path = _write(tmp_path, manifest)
    req = _extract_mint_fields(
        path,
        name=None,
        manufacturer=None,
        model=None,
        firmware_version=None,
        rcan_version=None,
        pq_signing_pub=None,
    )
    assert req.rcn_ids == ("RCN-000000000001", "RCN-000000000002")
    assert req.rmn == "RMN-000000000007"
    assert req.rhn_ids == ("RHN-000000000099",)


def test_signed_register_body_carries_sibling_ids(tmp_path, monkeypatch):
    """End-to-end: manifest with sibling IDs → signed POST body that RRF
    1.10.0 can verify. sign_body covers the new fields (body+ids canonical
    scheme from v0.9.1)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    manifest = BOB_MIN.replace(
        "  firmware_version: 1.0.0\n",
        "  firmware_version: 1.0.0\n"
        "  rcn_ids:\n    - RCN-000000000001\n"
        "  rmn: RMN-000000000007\n"
        "  rhn_ids:\n    - RHN-000000000099\n",
    )
    path = _write(tmp_path, manifest)

    captured = {}

    def fake_post(endpoint, body, timeout=15.0):
        captured["body"] = body
        from robot_md.register import MintResult

        return MintResult(
            rrn="RRN-000000000099",
            registered_at="x",
            record_url="u",
            raw={"api_key": "k"},
        )

    with patch("robot_md.register.post_to_rrf", fake_post):
        rc = cli_register(path, endpoint=DEFAULT_ENDPOINT)
    assert rc == 0

    body = captured["body"]
    assert body["rcn_ids"] == ["RCN-000000000001"]
    assert body["rmn"] == "RMN-000000000007"
    assert body["rhn_ids"] == ["RHN-000000000099"]
    # Signature covers the full body (body+ids canonical scheme)
    assert verify_body(body) is True


# ---- preflight: peek_next_rrn + cli_register integration -----------------


def test_peek_next_rrn_derives_peek_url_from_register_endpoint(monkeypatch):
    """peek_next_rrn rewrites .../register to .../_next."""
    captured = {}

    class _Resp:
        def __init__(self, payload):
            self._payload = json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self):
            return self._payload

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        return _Resp({"next_rrn": "RRN-000000000010", "reserved_floor": 10})

    with patch("urllib.request.urlopen", fake_urlopen):
        result = peek_next_rrn(DEFAULT_ENDPOINT)

    assert result == {"next_rrn": "RRN-000000000010", "reserved_floor": 10}
    assert captured["url"].endswith("/v2/robots/_next")
    # UA header must be set — Cloudflare blocks default Python-urllib UA at 403.
    ua = next((v for k, v in captured["headers"].items() if k.lower() == "user-agent"), None)
    assert ua is not None
    assert "robot-md" in ua.lower()


def test_peek_next_rrn_returns_none_on_404(monkeypatch):
    """Older RRF deployments without /_next 404 — preflight must be silent."""
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    with patch("urllib.request.urlopen", fake_urlopen):
        assert peek_next_rrn(DEFAULT_ENDPOINT) is None


def test_peek_next_rrn_returns_none_on_malformed_endpoint():
    """Endpoints that don't end in /register can't derive a peek URL."""
    assert peek_next_rrn("https://example.com/api/mint") is None


def test_peek_next_rrn_returns_none_on_malformed_json(monkeypatch):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self):
            return b"not json"

    with patch("urllib.request.urlopen", lambda *_a, **_kw: _Resp()):
        assert peek_next_rrn(DEFAULT_ENDPOINT) is None


def test_cli_register_prints_preflight_rrn_before_posting(tmp_path, monkeypatch, capsys):
    """The next-RRN preview must land on stderr before sign+POST happens."""
    monkeypatch.setenv("HOME", str(tmp_path))
    path = _write(tmp_path)

    def fake_peek(endpoint, timeout=5.0):
        return {"next_rrn": "RRN-000000000042", "reserved_floor": 10}

    def fake_post(endpoint, body, timeout=15.0):
        from robot_md.register import MintResult

        return MintResult(
            rrn="RRN-000000000042",
            registered_at="2026-05-11T00:00:00Z",
            record_url="https://robotregistryfoundation.org/v2/robots/RRN-000000000042",
            raw={"rrn": "RRN-000000000042", "api_key": "k"},
        )

    with (
        patch("robot_md.register.peek_next_rrn", fake_peek),
        patch("robot_md.register.post_to_rrf", fake_post),
    ):
        rc = cli_register(path, endpoint=DEFAULT_ENDPOINT)

    assert rc == 0
    err = capsys.readouterr().err
    assert "Next RRN: RRN-000000000042" in err
    assert "reserved for canonical robots" in err


def test_cli_register_proceeds_silently_when_preflight_fails(tmp_path, monkeypatch, capsys):
    """An older RRF (peek returns None) must not abort the mint."""
    monkeypatch.setenv("HOME", str(tmp_path))
    path = _write(tmp_path)

    def fake_post(endpoint, body, timeout=15.0):
        from robot_md.register import MintResult

        return MintResult(
            rrn="RRN-000000000099",
            registered_at="x",
            record_url="u",
            raw={"api_key": "k"},
        )

    with (
        patch("robot_md.register.peek_next_rrn", lambda *_a, **_kw: None),
        patch("robot_md.register.post_to_rrf", fake_post),
    ):
        rc = cli_register(path, endpoint=DEFAULT_ENDPOINT)

    assert rc == 0
    # No "Next RRN:" line should have been printed.
    assert "Next RRN:" not in capsys.readouterr().err
