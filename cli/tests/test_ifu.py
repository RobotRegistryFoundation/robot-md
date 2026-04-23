"""v0.9.4 — §24 IFU module tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ruamel.yaml")

from robot_md.ifu import (
    ART13_COVERAGE,
    DEFAULT_KNOWN_LIMITATIONS,
    DEFAULT_KNOWN_RISKS,
    DEFAULT_LIFETIME,
    IFU_SCHEMA_NAME,
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
  fria_ref: https://acme.example/fria/2026.pdf
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


def _bench(tmp_path: Path) -> Path:
    """A minimal §23-shaped benchmark artifact on disk."""
    path = tmp_path / "bench.json"
    path.write_text(
        json.dumps(
            {
                "schema": "rcan-safety-benchmark-v1",
                "generated_at": "2026-04-22T00:00:00.000000Z",
                "mode": "synthetic",
                "iterations": 3,
                "thresholds": {
                    "estop_p95_ms": 100.0,
                    "bounds_check_p95_ms": 5.0,
                    "confidence_gate_p95_ms": 2.0,
                    "full_pipeline_p95_ms": 50.0,
                },
                "results": {
                    "estop": {"p95_ms": 0.01, "pass": True},
                    "full_pipeline": {"p95_ms": 40.0, "pass": True},
                },
                "overall_pass": True,
            }
        )
    )
    return path


# ---- shape ----------------------------------------------------------


def test_ifu_schema_and_art13_coverage(tmp_path):
    art = build_artifact(_write(tmp_path))
    assert art["schema"] == IFU_SCHEMA_NAME
    assert set(art["art13_coverage"]) == set(ART13_COVERAGE)
    # All 8 Art. 13(3) sections present
    for section in ART13_COVERAGE:
        assert section in art


def test_ifu_provider_identity_from_metadata(tmp_path):
    art = build_artifact(_write(tmp_path))
    p = art["provider_identity"]
    assert p["rrn"] == "RRN-000000000042"
    assert p["robot_name"] == "bob"
    assert p["provider_name"] == "Acme Robotics"
    assert p["provider_contact"] == "safety@acme.example"
    assert p["rcan_version"] == "3.0"
    assert p["agent_provider"] == "anthropic"
    assert p["agent_model"] == "claude-sonnet-4-6"


def test_ifu_intended_purpose_uses_description_flag(tmp_path):
    art = build_artifact(_write(tmp_path), description="Explicit purpose.")
    assert art["intended_purpose"]["description"] == "Explicit purpose."
    assert art["intended_purpose"]["annex_iii_basis"] == "safety_component"


def test_ifu_intended_purpose_falls_back_to_manifest_description(tmp_path):
    art = build_artifact(_write(tmp_path))
    # Falls back to manifest metadata.description
    assert art["intended_purpose"]["description"] == "Indoor warehouse navigation."


def test_ifu_capabilities_list_sorted_and_deduped(tmp_path):
    art = build_artifact(_write(tmp_path))
    c = art["capabilities_and_limitations"]
    assert c["capabilities"] == ["grasp", "navigate"]
    assert c["known_limitations"] == list(DEFAULT_KNOWN_LIMITATIONS)


def test_ifu_oversight_pulls_hitl_and_estop_and_confidence(tmp_path):
    art = build_artifact(_write(tmp_path))
    o = art["human_oversight_measures"]
    assert o["estop"]["software"] is True
    assert o["estop"]["response_ms"] == 100
    assert o["hitl_gates"] == [{"scope": "system", "require_auth": True}]
    assert o["confidence_gate"] == 0.7


def test_ifu_known_risks_default(tmp_path):
    art = build_artifact(_write(tmp_path))
    assert art["known_risks_and_misuse"]["known_risks"] == list(DEFAULT_KNOWN_RISKS)


def test_ifu_lifetime_flag_overrides_default(tmp_path):
    art = build_artifact(_write(tmp_path), lifetime="Supported through 2028.")
    assert art["expected_lifetime"]["description"] == "Supported through 2028."


def test_ifu_lifetime_default_when_no_override(tmp_path):
    art = build_artifact(_write(tmp_path))
    assert art["expected_lifetime"]["description"] == DEFAULT_LIFETIME


def test_ifu_maintenance_references_rrn_specific_incident_log(tmp_path):
    art = build_artifact(_write(tmp_path))
    m = art["maintenance_requirements"]
    assert "RRN-000000000042" in m["incident_log"]
    assert "<rrn>" not in m["incident_log"]


def test_ifu_performance_without_benchmark_notes_missing(tmp_path):
    art = build_artifact(_write(tmp_path))
    perf = art["accuracy_and_performance"]
    assert perf["benchmark_ref"] is None
    assert "emit-benchmarks" in perf["note"]


def test_ifu_performance_embeds_benchmark_ref(tmp_path):
    art = build_artifact(_write(tmp_path), benchmark=_bench(tmp_path))
    perf = art["accuracy_and_performance"]
    assert perf["benchmark_schema"] == "rcan-safety-benchmark-v1"
    assert perf["overall_pass"] is True
    assert perf["per_path_p95_ms"]["estop"] == 0.01
    assert perf["per_path_p95_ms"]["full_pipeline"] == 40.0


# ---- signing ----------------------------------------------------


def test_ifu_sign_raises_without_keypair(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(RuntimeError, match="no signing keypair"):
        sign_artifact({"schema": IFU_SCHEMA_NAME}, rrn="RRN-000000000042")


def test_ifu_sign_and_verify_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from robot_md.signing import generate_keypair, save_keypair, verify_body

    save_keypair("RRN-000000000042", generate_keypair())
    art = build_artifact(_write(tmp_path))
    signed = sign_artifact(art, rrn="RRN-000000000042")
    # Must round-trip through JSON (canonical_json accepts only JSON values).
    _ = json.dumps(signed, sort_keys=True)
    assert verify_body(signed) is True
