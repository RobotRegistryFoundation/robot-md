"""Article 11 technical-documentation summary tests.

robot-md-art11-summary-v0: an aggregator that pulls together the eight
EU AI Act Art. 11 categories from the manifest + signed artifacts on disk
+ the post-market incident log. Honest schema name (not rcan-art11-v1)
since rcan-spec hasn't defined an Art. 11 wire format upstream.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ruamel.yaml")

from robot_md.art11 import (
    ART11_CATEGORIES,
    ART11_SCHEMA_NAME,
    build_artifact,
    sign_artifact,
)

BOB_MIN = """\
---
rcan_version: "3.2"
metadata:
  robot_name: bob
  manufacturer: SeeedStudio
  model: SO-ARM101
  firmware_version: 1.0.0
  rrn: RRN-000000000042
  rrn_uri: rrn://seeed/robot/so-arm101/bob
physics:
  type: arm+camera
  dof: 6
drivers:
  - { id: arm, protocol: feetech, port: /dev/null }
agent:
  runtimes:
    - id: opencastor
      models:
        - { provider: anthropic, model: claude-sonnet-4-6, role: primary }
safety:
  estop: { software: true, hardware: false, response_ms: 50 }
  duty_cycle_limits:
    wrist_flex: { max_continuous_deg: 45, cooldown_s: 30 }
capabilities:
  - manipulate.pick
  - perceive.depth
---
# bob
"""


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    p = tmp_path / "ROBOT.md"
    p.write_text(BOB_MIN)
    return p


def test_schema_name_is_aggregator_not_wire_format(manifest):
    art = build_artifact(manifest)
    # Honesty: this is an aggregator, not a published rcan-spec wire format.
    assert art["schema"] == ART11_SCHEMA_NAME
    assert ART11_SCHEMA_NAME == "robot-md-art11-summary-v0"
    assert "rcan-art11" not in ART11_SCHEMA_NAME  # don't claim spec status


def test_all_eight_art11_categories_present(manifest):
    art = build_artifact(manifest)
    for category in ART11_CATEGORIES:
        assert category in art, f"missing Art. 11 category: {category}"


def test_system_identity_pulled_from_manifest(manifest):
    art = build_artifact(manifest)
    sys = art["system_identity"]
    assert sys["rrn"] == "RRN-000000000042"
    assert sys["robot_name"] == "bob"
    assert sys["manufacturer"] == "SeeedStudio"
    assert sys["model"] == "SO-ARM101"
    assert sys["rcan_version"] == "3.2"


def test_safety_controls_includes_duty_cycle(manifest):
    """Bob's wrist_flex duty_cycle is declared but unenforced — the Art-11
    summary must surface it so the gap is auditable."""
    art = build_artifact(manifest)
    safety = art["safety_controls"]
    assert safety["estop"]["response_ms"] == 50
    assert "wrist_flex" in safety.get("duty_cycle_limits", {})


def test_model_provenance_from_agent_runtimes(manifest):
    art = build_artifact(manifest)
    models = art["model_provenance"]["models"]
    assert any(
        m.get("provider") == "anthropic" and m.get("model") == "claude-sonnet-4-6"
        for m in models
    )


def test_post_market_monitoring_includes_incident_log_path(manifest):
    art = build_artifact(manifest)
    pm = art["post_market_monitoring"]
    assert "incident_log" in pm
    assert "RRN-000000000042" in pm["incident_log"]
    assert pm["total_incidents"] == 0  # no log yet


def test_post_market_counts_incidents_when_log_present(manifest, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from robot_md.incidents import record
    record(
        "RRN-000000000042",
        severity="other",
        category="motor_stall",
        description="wrist_flex stalled",
    )
    art = build_artifact(manifest)
    assert art["post_market_monitoring"]["total_incidents"] == 1


def test_sbom_reference_when_path_passed(manifest, tmp_path):
    sbom = tmp_path / "sbom.json"
    sbom.write_text('{"bomFormat": "CycloneDX"}')
    art = build_artifact(manifest, sbom_path=sbom)
    assert art["sbom"]["path"] == str(sbom)
    assert art["sbom"]["present"] is True


def test_sbom_marked_missing_when_not_passed(manifest):
    art = build_artifact(manifest)
    assert art["sbom"]["present"] is False


def test_signed_artifacts_inventory(manifest, tmp_path):
    """When pointed at a directory of emitted signed artifacts, the summary
    inventories what's present so a notified body can locate them."""
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "fria.json").write_text(
        json.dumps({"schema": "rcan-fria-v1", "system": {"rrn": "RRN-000000000042"}})
    )
    (artifacts_dir / "ifu.json").write_text(
        json.dumps({"schema": "rcan-ifu-v1", "provider_identity": {"rrn": "RRN-000000000042"}})
    )
    art = build_artifact(manifest, signed_artifacts_dir=artifacts_dir)
    inv = art["notified_body_submission"]["artifacts"]
    schemas = {a["schema"] for a in inv}
    assert "rcan-fria-v1" in schemas
    assert "rcan-ifu-v1" in schemas


def test_sign_requires_keystore(manifest):
    art = build_artifact(manifest)
    with pytest.raises(RuntimeError, match="no signing keypair"):
        sign_artifact(art, rrn="RRN-000000000042")
