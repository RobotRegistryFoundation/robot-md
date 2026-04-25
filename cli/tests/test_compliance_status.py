"""Tests for `robot-md compliance status` — the one-shot pre-flight check.

Pulls together: manifest, keystore, audit chain, incidents log, on-disk
artifact inventory, RRF reachability + record drift, submission readiness.
Network probe is mockable for deterministic CI.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("ruamel.yaml")

from robot_md.compliance_status import (
    EXPECTED_ARTIFACT_SCHEMAS,
    format_status_text,
    gather_status,
)

BOB_MIN = """\
---
rcan_version: "3.2"
metadata:
  robot_name: bob
  manufacturer: Acme
  model: rx-1
  firmware_version: 1.0.0
  rrn: RRN-000000000099
network:
  rrf_endpoint: https://robotregistryfoundation.org
physics: { type: arm, dof: 6 }
drivers:
  - { id: arm, protocol: feetech, port: /dev/null }
safety:
  estop: { software: true, hardware: false, response_ms: 50 }
  max_joint_velocity_dps: 30
  hitl_gates:
    - { scope: navigate, require_auth: true }
capabilities: [navigate]
---
# bob
"""


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    p = tmp_path / "ROBOT.md"
    p.write_text(BOB_MIN)
    return p


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _mock_resp(status: int, body: dict | bytes = b"") -> object:
    class _R:
        def __init__(self):
            self.status = status
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self._fp = io.BytesIO(data)

        def read(self):
            return self._fp.read()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    return _R()


# ---- gather_status -----------------------------------------------------


def test_status_has_all_top_level_sections(manifest, home):
    s = gather_status(manifest, network_probe=False)
    for k in (
        "rrn",
        "manifest",
        "keystore",
        "audit",
        "incidents",
        "artifacts",
        "registry",
        "submission_readiness",
        "first_motion_readiness",
        "blockers",
    ):
        assert k in s, f"missing section: {k}"


def test_status_pulls_rrn_from_manifest(manifest, home):
    s = gather_status(manifest, network_probe=False)
    assert s["rrn"] == "RRN-000000000099"


def test_status_marks_apikey_missing_when_absent(manifest, home):
    s = gather_status(manifest, network_probe=False)
    assert s["keystore"]["apikey"]["present"] is False
    # Submission readiness reflects the apikey gap
    for kind in ("fria", "ifu", "safety-benchmark", "incident-report", "eu-register"):
        assert s["submission_readiness"][kind]["ready"] is False
        assert "apikey" in s["submission_readiness"][kind]["reason"].lower()


def test_status_marks_apikey_present_when_keystore_has_one(manifest, home):
    apikey_path = home / ".robot-md" / "keys" / "RRN-000000000099.apikey"
    apikey_path.parent.mkdir(parents=True, exist_ok=True)
    apikey_path.write_text("test-token")

    s = gather_status(manifest, network_probe=False)
    assert s["keystore"]["apikey"]["present"] is True
    for kind in ("fria", "ifu", "safety-benchmark", "incident-report", "eu-register"):
        assert s["submission_readiness"][kind]["ready"] is True


def test_status_audit_chain_walked(manifest, home):
    from robot_md.audit import record_event

    record_event("RRN-000000000099", event="test", details={})
    record_event("RRN-000000000099", event="test", details={})

    s = gather_status(manifest, network_probe=False)
    assert s["audit"]["valid"] is True
    assert s["audit"]["entries"] == 2


def test_status_inventories_compliance_artifacts(manifest, home, tmp_path):
    artifacts_dir = tmp_path / "compliance"
    artifacts_dir.mkdir()
    # FRIA uses nested signing_key (rcan-py FriaDocument shape)
    (artifacts_dir / "fria.json").write_text(
        json.dumps({"schema": "rcan-fria-v1", "sig": {"x": "y"}, "signing_key": {"alg": "h"}})
    )
    # IFU uses top-level pq_signing_pub (sign_body shape)
    (artifacts_dir / "ifu.json").write_text(json.dumps({"schema": "rcan-ifu-v1"}))
    # Incident uses top-level pq_signing_pub when signed
    (artifacts_dir / "incidents.json").write_text(
        json.dumps({"schema": "rcan-incidents-v1", "sig": {"x": "y"}, "pq_signing_pub": "abc"})
    )

    s = gather_status(manifest, artifacts_dir=artifacts_dir, network_probe=False)
    schemas = {a["schema"] for a in s["artifacts"]["present"]}
    assert "rcan-fria-v1" in schemas
    assert "rcan-ifu-v1" in schemas
    # Missing artifacts surface
    assert "rcan-safety-benchmark-v1" in s["artifacts"]["missing"]
    # Both signed-envelope shapes detected
    fria_entry = next(a for a in s["artifacts"]["present"] if a["schema"] == "rcan-fria-v1")
    incidents_entry = next(
        a for a in s["artifacts"]["present"] if a["schema"] == "rcan-incidents-v1"
    )
    ifu_entry = next(a for a in s["artifacts"]["present"] if a["schema"] == "rcan-ifu-v1")
    assert fria_entry["signed"] is True, "nested signing_key shape should be detected"
    assert incidents_entry["signed"] is True, "top-level pq_signing_pub shape should be detected"
    assert ifu_entry["signed"] is False, "missing both shapes → unsigned"


def test_status_detects_rcan_version_drift(manifest, home):
    """Manifest declares 3.2; record returns 3.0 → drift flagged in blockers."""

    def fake_urlopen(req, timeout=None):
        # Reachability check (list endpoint)
        if req.full_url.endswith("/v2/robots"):
            return _mock_resp(200, {"robots": []})
        # Record lookup
        return _mock_resp(200, {"rrn": "RRN-000000000099", "rcan_version": "3.0"})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        s = gather_status(manifest, network_probe=True)

    assert s["registry"]["reachable"] is True
    assert s["registry"]["record_present"] is True
    assert s["registry"]["record_rcan_version"] == "3.0"
    assert s["registry"]["manifest_rcan_version"] == "3.2"
    assert s["registry"]["version_drift"] is True
    # Drift surfaces in blockers
    assert any("rcan_version" in b.lower() for b in s["blockers"])


def test_status_no_drift_when_versions_match(manifest, home):
    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/v2/robots"):
            return _mock_resp(200, {"robots": []})
        return _mock_resp(200, {"rrn": "RRN-000000000099", "rcan_version": "3.2"})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        s = gather_status(manifest, network_probe=True)

    assert s["registry"]["version_drift"] is False


def test_status_handles_record_not_found(manifest, home):
    """RRN not registered (404) → record_present=False, no drift error."""
    import urllib.error

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/v2/robots"):
            return _mock_resp(200, {"robots": []})
        raise urllib.error.HTTPError(
            req.full_url, 404, "Not Found", {}, io.BytesIO(b'{"error":"nope"}')
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        s = gather_status(manifest, network_probe=True)

    assert s["registry"]["reachable"] is True
    assert s["registry"]["record_present"] is False


def test_blockers_aggregates_top_issues(manifest, home):
    """No apikey + missing artifacts → blockers list covers both."""
    s = gather_status(manifest, network_probe=False)
    blockers_text = " | ".join(s["blockers"]).lower()
    assert "apikey" in blockers_text
    assert "missing" in blockers_text or "artifact" in blockers_text


def test_expected_artifact_schemas_match_emit_commands():
    """Sanity: the schemas this command checks for should match what the
    emit-* commands actually produce."""
    assert "rcan-fria-v1" in EXPECTED_ARTIFACT_SCHEMAS
    assert "rcan-ifu-v1" in EXPECTED_ARTIFACT_SCHEMAS
    assert "rcan-safety-benchmark-v1" in EXPECTED_ARTIFACT_SCHEMAS
    assert "rcan-incidents-v1" in EXPECTED_ARTIFACT_SCHEMAS
    assert "rcan-eu-register-v1" in EXPECTED_ARTIFACT_SCHEMAS


# ---- format_status_text ------------------------------------------------


def test_format_text_includes_rrn_and_status_summary(manifest, home):
    s = gather_status(manifest, network_probe=False)
    out = format_status_text(s)
    assert "RRN-000000000099" in out
    assert "blocker" in out.lower() or "ready" in out.lower()


def test_format_text_no_blockers_when_clean(manifest, home, tmp_path):
    """Signing keypair + apikey + all artifacts + no drift → 0 blockers."""
    from robot_md.signing import generate_keypair, save_keypair

    save_keypair("RRN-000000000099", generate_keypair())

    apikey_path = home / ".robot-md" / "keys" / "RRN-000000000099.apikey"
    apikey_path.write_text("test-token")

    artifacts_dir = tmp_path / "compliance"
    artifacts_dir.mkdir()
    for schema in EXPECTED_ARTIFACT_SCHEMAS:
        kind = schema.replace("rcan-", "").replace("-v1", "")
        (artifacts_dir / f"{kind}.json").write_text(
            json.dumps({"schema": schema, "sig": {"x": "y"}, "signing_key": {"x": "y"}})
        )

    s = gather_status(manifest, artifacts_dir=artifacts_dir, network_probe=False)
    assert s["blockers"] == []


# ---- first-motion readiness ---------------------------------------------


BOB_NOT_READY = """\
---
rcan_version: "3.2"
metadata:
  robot_name: bob
  manufacturer: Acme
  model: SO-ARM101
  firmware_version: 1.0.0
  rrn: RRN-000000000077
network:
  rrf_endpoint: https://robotregistryfoundation.org
physics:
  type: arm
  dof: 6
drivers:
  - { id: arm, protocol: feetech_scs, port: /dev/null }
  - { id: vision, protocol: oak_d_lr, connection: usb }
capabilities:
  - manipulate.pick
  - manipulate.place
safety:
  estop: { software: true, response_ms: 50 }
---
# bob (not first-motion-ready)
"""


@pytest.fixture
def bob_not_ready(tmp_path: Path) -> Path:
    p = tmp_path / "ROBOT_NOT_READY.md"
    p.write_text(BOB_NOT_READY)
    return p


def test_first_motion_readiness_section_present(manifest, home):
    s = gather_status(manifest, network_probe=False)
    fmr = s["first_motion_readiness"]
    assert "applies" in fmr
    assert "ready" in fmr
    assert "checks" in fmr
    for cid in (
        "hitl_gates",
        "max_joint_velocity_dps",
        "object_descriptors",
        "camera_extrinsic",
        "capability_namespace",
    ):
        assert cid in fmr["checks"], f"missing first-motion check: {cid}"


def test_first_motion_readiness_clean_for_well_formed_manifest(manifest, home):
    """BOB_MIN has gates + velocity-limit + only `navigate` cap (no .pick) +
    no vision driver → all 5 checks pass."""
    s = gather_status(manifest, network_probe=False)
    fmr = s["first_motion_readiness"]
    assert fmr["ready"] is True
    for cid, c in fmr["checks"].items():
        assert c["ok"] is True, f"{cid} unexpectedly not ok: {c}"


def test_first_motion_readiness_flags_bobs_actual_gaps(bob_not_ready, home):
    """The exact 5 gaps bob's hand-rolled manifest exposed on 2026-04-25."""
    s = gather_status(bob_not_ready, network_probe=False)
    fmr = s["first_motion_readiness"]
    assert fmr["applies"] is True
    assert fmr["ready"] is False

    checks = fmr["checks"]
    # 1. No hitl_gates declared with motion capabilities
    assert checks["hitl_gates"]["ok"] is False
    assert "hitl_gates" in checks["hitl_gates"]["detail"].lower()
    # 2. Actuation driver but no max_joint_velocity_dps
    assert checks["max_joint_velocity_dps"]["ok"] is False
    assert "max_joint_velocity_dps" in checks["max_joint_velocity_dps"]["detail"]
    # 3. *.pick declared but no descriptors
    assert checks["object_descriptors"]["ok"] is False
    assert "descriptor" in checks["object_descriptors"]["detail"].lower()
    # 4. Vision driver but no extrinsic
    assert checks["camera_extrinsic"]["ok"] is False
    assert "extrinsic" in checks["camera_extrinsic"]["detail"].lower()
    # 5. manipulate.* capabilities but feetech_scs implements arm.*
    assert checks["capability_namespace"]["ok"] is False
    assert "manipulate" in checks["capability_namespace"]["detail"]


def test_first_motion_readiness_bubbles_to_blockers(bob_not_ready, home):
    s = gather_status(bob_not_ready, network_probe=False)
    blocker_text = "\n".join(s["blockers"])
    for cid in (
        "hitl_gates",
        "max_joint_velocity_dps",
        "object_descriptors",
        "camera_extrinsic",
        "capability_namespace",
    ):
        assert cid in blocker_text, f"first-motion check {cid} not aggregated into blockers"


def test_first_motion_readiness_does_not_apply_for_pure_sensor_manifest(tmp_path, home):
    """A manifest with no actuation driver, no motion capabilities, no
    vision driver should not surface first-motion blockers — fmr.applies=False."""
    sensor_only = tmp_path / "ROBOT_sensor.md"
    sensor_only.write_text("""\
---
rcan_version: "3.2"
metadata:
  robot_name: lonely-thermometer
  manufacturer: Acme
  model: probe
  firmware_version: 1.0.0
physics: { type: sensor, dof: 0 }
drivers:
  - { id: temp, protocol: i2c, port: /dev/null }
safety:
  estop: { software: true, response_ms: 50 }
capabilities: [perceive.temperature]
---
""")
    s = gather_status(sensor_only, network_probe=False)
    fmr = s["first_motion_readiness"]
    assert fmr["applies"] is False, "pure-sensor manifest should not trigger first-motion checks"


def test_first_motion_readiness_passes_when_all_5_gaps_filled(tmp_path, home):
    ready = tmp_path / "ROBOT_ready.md"
    ready.write_text("""\
---
rcan_version: "3.2"
metadata:
  robot_name: ready-bob
  manufacturer: Acme
  model: SO-ARM101
  firmware_version: 1.0.0
  rrn: RRN-000000000088
network:
  rrf_endpoint: https://robotregistryfoundation.org
physics:
  type: arm
  dof: 6
  solver:
    cameras:
      - driver_id: cam
        primary_stream: rgb
        mount: world
        extrinsic: { R: [[1,0,0],[0,1,0],[0,0,1]], t: [0.0, 0.0, 0.5] }
drivers:
  - { id: arm, protocol: feetech_scs, port: /dev/null }
  - { id: vision, protocol: oak_d_lr, connection: usb }
vision:
  object_descriptors:
    - { id: red_lego, detector: hsv, params: { h: [0, 10] } }
capabilities:
  - arm.pick
  - arm.place
  - perceive.rgb
safety:
  estop: { software: true, response_ms: 50 }
  max_joint_velocity_dps: 30
  hitl_gates:
    - { scope: arm, require_auth: true }
---
""")
    s = gather_status(ready, network_probe=False)
    fmr = s["first_motion_readiness"]
    assert fmr["applies"] is True
    assert fmr["ready"] is True, f"expected ready=True; checks: {fmr['checks']}"


def test_format_text_includes_first_motion_section(bob_not_ready, home):
    s = gather_status(bob_not_ready, network_probe=False)
    out = format_status_text(s)
    assert "First-motion readiness" in out
    # Each failed check shows its fix line
    assert "hitl_gates" in out
    assert "extrinsic" in out
