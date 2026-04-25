"""§22 FRIA module tests — Article 27 Fundamental Rights Impact Assessment."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("ruamel.yaml")

from robot_md.fria import (
    FRIA_SCHEMA_NAME,
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
  description: Indoor warehouse navigation.
physics:
  type: arm
  dof: 6
drivers:
  - { id: arm, protocol: feetech, port: /dev/ttyACM0 }
safety:
  estop: { software: true, hardware: false, response_ms: 100 }
  hitl_gates:
    - { scope: system, require_auth: true }
brain:
  planning_provider: anthropic
  planning_model: claude-sonnet-4-6
  confidence_gate: 0.7
compliance:
  annex_iii_basis: safety_component
  deployment_context: internal-warehouse-pilot
  affected_groups:
    - warehouse-operators
    - maintenance-staff
  known_risks:
    - "Unauthorized motion outside declared workspace bounds."
capabilities:
  - navigate
  - grasp
---
# bob
"""


def _write(tmp_path: Path, content: str = BOB_MIN) -> Path:
    p = tmp_path / "bob.ROBOT.md"
    p.write_text(content)
    return p


# ---- shape ---------------------------------------------------------------


def test_fria_schema_name(tmp_path):
    art = build_artifact(_write(tmp_path))
    assert art["schema"] == FRIA_SCHEMA_NAME


def test_fria_required_fields_present(tmp_path):
    art = build_artifact(_write(tmp_path))
    # FriaDocument shape: schema, generated_at, system, deployment, signing_key, sig, conformance
    for field in ("schema", "generated_at", "system", "deployment", "signing_key", "sig"):
        assert field in art, f"missing required FRIA field: {field}"


def test_fria_system_identity_pulled_from_manifest(tmp_path):
    art = build_artifact(_write(tmp_path))
    sys = art["system"]
    assert sys["rrn"] == "RRN-000000000042"
    assert sys["robot_name"] == "bob"
    assert sys["manufacturer"] == "Acme Robotics"
    assert sys["model"] == "rx-1"
    assert sys["rcan_version"] == "3.0"
    assert sorted(sys["capabilities"]) == ["grasp", "navigate"]


def test_fria_deployment_context(tmp_path):
    art = build_artifact(_write(tmp_path))
    dep = art["deployment"]
    assert dep["annex_iii_basis"] == "safety_component"
    assert dep["deployment_context"] == "internal-warehouse-pilot"
    assert "warehouse-operators" in dep["affected_groups"]


def test_fria_deployment_overrides_manifest(tmp_path):
    art = build_artifact(
        _write(tmp_path),
        deployment_context="acceptance-trial-2026Q2",
        affected_groups=["test-engineers"],
    )
    dep = art["deployment"]
    assert dep["deployment_context"] == "acceptance-trial-2026Q2"
    assert dep["affected_groups"] == ["test-engineers"]


def test_fria_unsigned_sig_is_empty(tmp_path):
    art = build_artifact(_write(tmp_path))
    # Pre-sign: sig is an empty dict (the type contract is dict, not None)
    assert art["sig"] == {}
    assert (
        art["signing_key"] == {}
        or art["signing_key"] is None
        or (isinstance(art["signing_key"], dict) and not art["signing_key"].get("public_key"))
    )


def test_fria_oversight_pulled_from_safety(tmp_path):
    art = build_artifact(_write(tmp_path))
    dep = art["deployment"]
    oversight = dep["human_oversight"]
    assert oversight["estop"]["software"] is True
    assert oversight["estop"]["response_ms"] == 100
    assert len(oversight["hitl_gates"]) == 1
    assert oversight["hitl_gates"][0]["scope"] == "system"


def test_fria_known_risks_from_manifest(tmp_path):
    art = build_artifact(_write(tmp_path))
    risks = art["deployment"]["known_risks"]
    assert any("workspace bounds" in r for r in risks)


# ---- sign ----------------------------------------------------------------


def test_sign_artifact_requires_keystore(tmp_path):
    art = build_artifact(_write(tmp_path))
    with pytest.raises(RuntimeError, match="no signing keypair"):
        sign_artifact(art, rrn="RRN-000000000042")
