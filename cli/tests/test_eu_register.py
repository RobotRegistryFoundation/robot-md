"""v0.9.5 — §26 EU Register submission artifact tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ruamel.yaml")

from robot_md.eu_register import (
    CONFORMITY_STATUS_DECLARED,
    EU_REGISTER_SCHEMA_NAME,
    SUBMISSION_INSTRUCTIONS,
    EuRegisterError,
    build_artifact,
    sign_artifact,
)

BOB_MIN = """\
---
rcan_version: "3.0"
metadata:
  robot_name: bob
  manufacturer: Acme Robotics
  model: rx-1
  firmware_version: 1.0.0
  author: safety@acme.example
  rrn: RRN-000000000042
  rrn_uri: rrn://acme/robot/rx-1/bob
physics:
  type: arm
  dof: 6
drivers:
  - { id: arm, protocol: feetech, port: /dev/ttyACM0 }
safety:
  estop: { software: true, response_ms: 100 }
compliance:
  annex_iii_basis: safety_component
  fria_ref: https://acme.example/fria/2026.pdf
---
# bob
"""


def _write_manifest(tmp_path: Path, content: str = BOB_MIN) -> Path:
    p = tmp_path / "bob.ROBOT.md"
    p.write_text(content)
    return p


def _write_fria(tmp_path: Path) -> Path:
    p = tmp_path / "fria-RRN-000000000042-signed.json"
    p.write_text('{"schema":"rcan-fria-v1","signed":true}')
    return p


# ---- happy path -------------------------------------------------


def test_emits_schema_and_all_must_fields(tmp_path):
    art = build_artifact(
        _write_manifest(tmp_path),
        fria_path=_write_fria(tmp_path),
    )
    assert art["schema"] == EU_REGISTER_SCHEMA_NAME
    assert art["generated_at"].endswith("Z")
    assert art["fria_ref"] == "fria-RRN-000000000042-signed.json"  # basename only
    assert art["provider"] == {
        "name": "Acme Robotics",
        "contact": "safety@acme.example",
    }
    assert art["system"]["rrn"] == "RRN-000000000042"
    assert art["system"]["rrn_uri"] == "rrn://acme/robot/rx-1/bob"
    assert art["system"]["robot_name"] == "bob"
    assert art["system"]["rcan_version"] == "3.0"
    assert art["annex_iii_basis"] == "safety_component"
    assert art["conformity_status"] == CONFORMITY_STATUS_DECLARED
    assert art["submission_instructions"] == SUBMISSION_INSTRUCTIONS


def test_opencastor_version_is_optional(tmp_path):
    art = build_artifact(
        _write_manifest(tmp_path),
        fria_path=_write_fria(tmp_path),
    )
    assert art["system"]["opencastor_version"] == ""


def test_opencastor_version_flows_through(tmp_path):
    art = build_artifact(
        _write_manifest(tmp_path),
        fria_path=_write_fria(tmp_path),
        opencastor_version="2026.4.22.0",
    )
    assert art["system"]["opencastor_version"] == "2026.4.22.0"


def test_fria_ref_uses_basename_not_full_path(tmp_path):
    # Even if --fria is a nested path, the package references by basename.
    nested = tmp_path / "nested" / "dir"
    nested.mkdir(parents=True)
    fria = nested / "my-fria.json"
    fria.write_text("{}")
    art = build_artifact(_write_manifest(tmp_path), fria_path=fria)
    assert art["fria_ref"] == "my-fria.json"


# ---- validation errors -----------------------------------------


def test_errors_when_fria_missing(tmp_path):
    with pytest.raises(EuRegisterError, match="FRIA file not found"):
        build_artifact(
            _write_manifest(tmp_path),
            fria_path=tmp_path / "does-not-exist.json",
        )


def test_errors_when_rrn_missing(tmp_path):
    manifest = BOB_MIN.replace("  rrn: RRN-000000000042\n", "")
    with pytest.raises(EuRegisterError, match=r"metadata\.rrn"):
        build_artifact(
            _write_manifest(tmp_path, manifest),
            fria_path=_write_fria(tmp_path),
        )


def test_errors_when_annex_iii_basis_missing(tmp_path):
    manifest = BOB_MIN.replace("  annex_iii_basis: safety_component\n", "")
    with pytest.raises(EuRegisterError, match="annex_iii_basis"):
        build_artifact(
            _write_manifest(tmp_path, manifest),
            fria_path=_write_fria(tmp_path),
        )


def test_errors_when_manufacturer_missing(tmp_path):
    manifest = BOB_MIN.replace("  manufacturer: Acme Robotics\n", "")
    with pytest.raises(EuRegisterError, match="manufacturer"):
        build_artifact(
            _write_manifest(tmp_path, manifest),
            fria_path=_write_fria(tmp_path),
        )


def test_errors_when_author_missing(tmp_path):
    manifest = BOB_MIN.replace("  author: safety@acme.example\n", "")
    with pytest.raises(EuRegisterError, match="author"):
        build_artifact(
            _write_manifest(tmp_path, manifest),
            fria_path=_write_fria(tmp_path),
        )


# ---- signing -------------------------------------------------


def test_sign_raises_without_keypair(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(RuntimeError, match="no signing keypair"):
        sign_artifact({"schema": EU_REGISTER_SCHEMA_NAME}, rrn="RRN-000000000042")


def test_sign_and_verify_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from robot_md.signing import generate_keypair, save_keypair, verify_body

    save_keypair("RRN-000000000042", generate_keypair())
    art = build_artifact(
        _write_manifest(tmp_path),
        fria_path=_write_fria(tmp_path),
    )
    signed = sign_artifact(art, rrn="RRN-000000000042")
    _ = json.dumps(signed, sort_keys=True)
    assert verify_body(signed) is True
