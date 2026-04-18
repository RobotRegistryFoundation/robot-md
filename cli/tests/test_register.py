"""Tests for `robot-md register` — manifest field extraction + rewrite.

The live-endpoint POST is exercised via a mocked urlopen; real hits against
https://robotregistryfoundation.org would pollute the public registry.
"""
# ruff: noqa: SIM117  (nested `with` in pytest style is idiomatic for mock + raises)

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("ruamel.yaml")

from robot_md.register import (
    DEFAULT_ENDPOINT,
    MintRequest,
    _extract_mint_fields,
    cli_register,
    post_to_rrf,
    write_rrn_to_manifest,
)

BOB_MIN = """\
---
rcan_version: "3.0"
metadata:
  robot_name: bob
  manufacturer: craigm26
  model: opencastor-rpi5-hailo-soarm101
  version: 1.0
  author: craigm26@example.com
physics:
  type: arm
  dof: 6
  kinematics:
    - { id: shoulder, axis: z, length_mm: 60 }
drivers:
  - { id: arm, protocol: feetech, port: /dev/ttyACM0 }
safety:
  estop: { software: true, response_ms: 100 }
---

# bob

## Identity
Test.

## What bob Can Do
Test.

## Safety Gates
Test.
"""


def _write(tmp_path: Path, content: str = BOB_MIN) -> Path:
    p = tmp_path / "bob.ROBOT.md"
    p.write_text(content)
    return p


# ---- field extraction -----------------------------------------------------


def test_extract_from_manifest(tmp_path):
    path = _write(tmp_path)
    req = _extract_mint_fields(
        path,
        manufacturer=None,
        model=None,
        version=None,
        device_id=None,
        description=None,
        contact_email=None,
        source=None,
    )
    assert req.manufacturer == "craigm26"
    assert req.model == "opencastor-rpi5-hailo-soarm101"
    assert req.version == "1.0"
    # device_id falls back to robot_name
    assert req.device_id == "bob"
    # contact_email falls back to author
    assert req.contact_email == "craigm26@example.com"
    assert req.source == "robot-md-cli"


def test_cli_overrides_win(tmp_path):
    path = _write(tmp_path)
    req = _extract_mint_fields(
        path,
        manufacturer="acme",
        model="rx-1",
        version="2.0",
        device_id="a-1",
        description="prototype",
        contact_email="ops@acme.com",
        source="acme-fleet",
    )
    assert req.manufacturer == "acme"
    assert req.model == "rx-1"
    assert req.version == "2.0"
    assert req.device_id == "a-1"
    assert req.description == "prototype"
    assert req.contact_email == "ops@acme.com"
    assert req.source == "acme-fleet"


def test_missing_required_fields_raises(tmp_path):
    """Without manufacturer/model and no CLI overrides, we must refuse."""
    path = tmp_path / "minimal.ROBOT.md"
    path.write_text(
        BOB_MIN.replace("manufacturer: craigm26\n  ", "").replace(
            "model: opencastor-rpi5-hailo-soarm101\n  ", ""
        )
    )
    with pytest.raises(ValueError, match="missing required mint fields"):
        _extract_mint_fields(
            path,
            manufacturer=None,
            model=None,
            version=None,
            device_id=None,
            description=None,
            contact_email=None,
            source=None,
        )


def test_missing_robot_name_is_hard_error(tmp_path):
    path = tmp_path / "anon.ROBOT.md"
    path.write_text(BOB_MIN.replace("robot_name: bob", 'robot_name: ""'))
    with pytest.raises(ValueError, match="robot_name"):
        _extract_mint_fields(
            path,
            manufacturer="x",
            model="y",
            version="1",
            device_id="z",
            description=None,
            contact_email=None,
            source=None,
        )


def test_as_body_strips_empty_optional(tmp_path):
    req = MintRequest(
        manufacturer="a",
        model="b",
        version="1",
        device_id="c",
        description="",
        contact_email="",
        source="x",
    )
    body = req.as_body()
    assert "description" not in body
    assert "contact_email" not in body
    assert body["manufacturer"] == "a"
    assert body["source"] == "x"


# ---- network (mocked) -----------------------------------------------------


def _mock_urlopen_ok(response_json, status=201):
    """Helper: build a context manager that returns a fake urlopen response."""

    class FakeResponse:
        def __init__(self, data, code):
            self._data = data.encode("utf-8") if isinstance(data, str) else data
            self.status = code

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    text = json.dumps(response_json)
    return patch(
        "robot_md.register.urllib.request.urlopen", return_value=FakeResponse(text, status)
    )


def test_post_to_rrf_success():
    payload = {
        "rrn": "RRN-000000000999",
        "rcan_uri": "rrn://test/robot/demo/x",
        "api_key": "secret-xyz",
        "already_existed": False,
    }
    with _mock_urlopen_ok(payload, 201):
        result = post_to_rrf(DEFAULT_ENDPOINT, {"manufacturer": "a"})
    assert result.rrn == "RRN-000000000999"
    assert result.api_key == "secret-xyz"
    assert result.already_existed is False


def test_post_to_rrf_already_existed():
    payload = {
        "rrn": "RRN-000000000001",
        "rcan_uri": "rrn://test/robot/demo/x",
        "already_existed": True,
    }
    with _mock_urlopen_ok(payload, 200):
        result = post_to_rrf(DEFAULT_ENDPOINT, {"manufacturer": "a"})
    assert result.rrn == "RRN-000000000001"
    assert result.already_existed is True
    assert result.api_key is None


def test_post_to_rrf_http_error_wrapped():
    import urllib.error

    err = urllib.error.HTTPError(
        DEFAULT_ENDPOINT,
        400,
        "Bad Request",
        {},
        __import__("io").BytesIO(b'{"error":"missing fields"}'),
    )
    with patch("robot_md.register.urllib.request.urlopen", side_effect=err):
        with pytest.raises(RuntimeError, match="RRF returned 400"):
            post_to_rrf(DEFAULT_ENDPOINT, {})


def test_post_to_rrf_missing_rrn_in_response():
    with _mock_urlopen_ok({"message": "ok"}, 201):
        with pytest.raises(RuntimeError, match="missing 'rrn'"):
            post_to_rrf(DEFAULT_ENDPOINT, {})


# ---- filesystem side-effects ---------------------------------------------


def test_write_apikey_mode_600(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    import robot_md.register as reg

    monkeypatch.setattr(reg, "KEYSTORE_DIR", tmp_path / ".robot-md" / "keys")
    p = reg.write_apikey("RRN-000000000999", "secret-xyz")
    assert p.exists()
    import stat

    st = p.stat()
    assert stat.S_IMODE(st.st_mode) == 0o600
    assert p.read_text().strip() == "secret-xyz"


def test_write_rrn_to_manifest_preserves_body_and_comments(tmp_path):
    path = _write(tmp_path)
    write_rrn_to_manifest(path, "RRN-000000000042", "rrn://test/robot/demo/bob")
    txt = path.read_text()
    # New RRN landed
    assert "rrn: RRN-000000000042" in txt
    # rcan_uri landed
    assert "rrn://test/robot/demo/bob" in txt
    # Body preserved
    assert "## What bob Can Do" in txt
    # H1 preserved
    assert "# bob" in txt


def test_write_rrn_to_manifest_rejects_malformed(tmp_path):
    path = tmp_path / "bad.md"
    path.write_text("no frontmatter here")
    with pytest.raises(RuntimeError, match="frontmatter"):
        write_rrn_to_manifest(path, "RRN-1", "")


# ---- end-to-end dry-run ---------------------------------------------------


def test_cli_register_dry_run_no_network(tmp_path, capsys):
    path = _write(tmp_path)
    # Dry run must not invoke urlopen at all
    with patch("robot_md.register.urllib.request.urlopen") as spy:
        rc = cli_register(str(path), dry_run=True)
        spy.assert_not_called()
    assert rc == 0


def test_cli_register_end_to_end_with_mocked_network(tmp_path):
    path = _write(tmp_path)
    payload = {
        "rrn": "RRN-000000000055",
        "rcan_uri": "rrn://craigm26/robot/opencastor-rpi5-hailo-soarm101/bob",
        "api_key": "fake-key-xyz",
        "already_existed": False,
    }
    # Redirect keystore to tmp
    from robot_md import register as reg

    with _mock_urlopen_ok(payload, 201), patch.object(reg, "KEYSTORE_DIR", tmp_path / ".keys"):
        rc = cli_register(str(path))
    assert rc == 0
    # Manifest should now carry the new RRN
    assert "rrn: RRN-000000000055" in path.read_text()
    # API key file saved with 600
    key_path = tmp_path / ".keys" / "RRN-000000000055.apikey"
    assert key_path.exists()
    assert key_path.read_text().strip() == "fake-key-xyz"
    import stat

    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600


def test_cli_register_missing_file_returns_2(tmp_path):
    rc = cli_register(str(tmp_path / "no-such-file.ROBOT.md"), dry_run=True)
    assert rc == 2


def test_cli_register_rejects_missing_fields_with_exit_2(tmp_path):
    p = tmp_path / "incomplete.ROBOT.md"
    p.write_text(BOB_MIN.replace("manufacturer: craigm26\n  ", ""))
    rc = cli_register(str(p), dry_run=True)
    assert rc == 2
