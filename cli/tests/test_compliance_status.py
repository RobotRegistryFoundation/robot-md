# ruff: noqa: E501  -- YAML test fixtures (kinematics entries) are flow-style
# one-liners; splitting them across multiple lines hurts readability for the
# small diff this saves.
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
physics:
  type: arm
  dof: 2
  workspace:
    bounds_mm: { x: [0, 300], y: [-200, 200], z: [0, 250] }
  solver:
    ik_provider: stub
  kinematics:
    - { id: j1, axis: z, limits_deg: [-180, 180], a_mm: 0, d_mm: 60, servo_id: 1, encoder_sign: 1, zero_pose_steps: 1500 }
    - { id: j2, axis: y, limits_deg: [-90, 90], a_mm: 100, d_mm: 0, servo_id: 2, encoder_sign: 1, zero_pose_steps: 2200 }
drivers:
  - { id: arm, protocol: feetech, port: /dev/null }
safety:
  estop: { software: true, hardware: false, response_ms: 50 }
  max_joint_velocity_dps: 30
  hitl_gates:
    - { scope: arm, require_auth: true }
capabilities: [arm.home]
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
        "backend_resolution",
        "device_availability",
        "workspace_bounds_mm",
        "kinematics_complete",
        "solver_block",
        "joint_zero_sign",
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
    # 6. feetech_scs / oak_d_lr have no registered backend at all (the only
    # built-in backend exposes feetech + depthai protocols)
    assert checks["backend_resolution"]["ok"] is False
    assert (
        "feetech_scs" in checks["backend_resolution"]["detail"]
        or "oak_d_lr" in checks["backend_resolution"]["detail"]
    )


def test_first_motion_readiness_bubbles_to_blockers(bob_not_ready, home):
    s = gather_status(bob_not_ready, network_probe=False)
    blocker_text = "\n".join(s["blockers"])
    for cid in (
        "hitl_gates",
        "max_joint_velocity_dps",
        "object_descriptors",
        "camera_extrinsic",
        "capability_namespace",
        "backend_resolution",
        "workspace_bounds_mm",
        "kinematics_complete",
        "solver_block",
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
  dof: 2
  workspace:
    bounds_mm: { x: [0, 300], y: [-200, 200], z: [0, 250] }
  solver:
    ik_provider: stub
    cameras:
      - driver_id: cam
        primary_stream: rgb
        mount: world
        extrinsic: { R: [[1,0,0],[0,1,0],[0,0,1]], t: [0.0, 0.0, 0.5] }
  kinematics:
    - { id: j1, axis: z, limits_deg: [-180, 180], a_mm: 0, d_mm: 60, servo_id: 1, encoder_sign: 1, zero_pose_steps: 1500 }
    - { id: j2, axis: y, limits_deg: [-90, 90], a_mm: 100, d_mm: 0, servo_id: 2, encoder_sign: 1, zero_pose_steps: 2200 }
drivers:
  - { id: arm, protocol: feetech, port: /dev/null }
  - { id: vision, protocol: depthai, connection: usb }
vision:
  object_descriptors:
    - { id: red_lego, detector: hsv, params: { h_ranges: [[0, 10]], s_min: 120 } }
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


# ---- backend_resolution check (PR follow-up, 2026-04-25) -----------------


def test_backend_resolution_passes_for_canonical_protocols(tmp_path, home):
    """A manifest declaring `feetech` + `depthai` (the canonical protocols
    the bundled backend registers under) should pass backend_resolution."""
    p = tmp_path / "ROBOT.md"
    p.write_text("""\
---
rcan_version: "3.2"
metadata: { robot_name: bob, manufacturer: Acme, model: rx, firmware_version: 1.0.0 }
physics: { type: arm, dof: 6 }
drivers:
  - { id: arm, protocol: feetech, port: /dev/null }
  - { id: vision, protocol: depthai, connection: usb }
capabilities: [arm.home]
safety:
  estop: { software: true, response_ms: 50 }
  max_joint_velocity_dps: 30
  hitl_gates: [{ scope: arm, require_auth: true }]
---
""")
    s = gather_status(p, network_probe=False)
    assert s["first_motion_readiness"]["checks"]["backend_resolution"]["ok"] is True


def test_backend_resolution_flags_unregistered_protocols(tmp_path, home):
    """`feetech_scs` and `oak_d_lr` look reasonable but aren't claimed by any
    registered backend — the bundled `FeetechDepthaiBackend.protocols` is
    `{feetech, depthai}`. Dispatch will fail at no_backend, so this is a
    first-motion blocker."""
    p = tmp_path / "ROBOT.md"
    p.write_text("""\
---
rcan_version: "3.2"
metadata: { robot_name: bob, manufacturer: Acme, model: rx, firmware_version: 1.0.0 }
physics: { type: arm, dof: 6 }
drivers:
  - { id: arm, protocol: feetech_scs, port: /dev/null }
  - { id: vision, protocol: oak_d_lr, connection: usb }
capabilities: [arm.home]
safety:
  estop: { software: true, response_ms: 50 }
  max_joint_velocity_dps: 30
  hitl_gates: [{ scope: arm, require_auth: true }]
---
""")
    s = gather_status(p, network_probe=False)
    check = s["first_motion_readiness"]["checks"]["backend_resolution"]
    assert check["ok"] is False
    assert "feetech_scs" in check["detail"] and "oak_d_lr" in check["detail"]
    # Fix-line names canonical replacements
    assert "feetech" in check["fix"] and "depthai" in check["fix"]


# ---- device_availability check (PR follow-up, 2026-04-25) ----------------


def test_device_availability_skipped_for_dev_null(manifest, home):
    """BOB_MIN uses `port: /dev/null` as a fixture sentinel — the probe
    should skip non-serial-port-shaped paths so existing tests don't trip."""
    s = gather_status(manifest, network_probe=False)
    check = s["first_motion_readiness"]["checks"]["device_availability"]
    assert check["ok"] is True
    # Probe ran but skipped the non-tty path
    probes = check.get("probes", [])
    assert any(p.get("state") == "skipped" for p in probes), (
        f"expected at least one skipped probe; got {probes}"
    )


def test_device_availability_reports_missing_for_nonexistent_tty(tmp_path, home):
    """If the manifest names a /dev/tty* path that doesn't exist, the probe
    reports 'missing' (operator may not have plugged in yet) — not a blocker."""
    p = tmp_path / "ROBOT.md"
    p.write_text("""\
---
rcan_version: "3.2"
metadata: { robot_name: bob, manufacturer: Acme, model: rx, firmware_version: 1.0.0 }
physics: { type: arm, dof: 6 }
drivers:
  - { id: arm, protocol: feetech, port: /dev/ttyDOES_NOT_EXIST_99 }
capabilities: [arm.home]
safety:
  estop: { software: true, response_ms: 50 }
  max_joint_velocity_dps: 30
  hitl_gates: [{ scope: arm, require_auth: true }]
---
""")
    s = gather_status(p, network_probe=False)
    check = s["first_motion_readiness"]["checks"]["device_availability"]
    # Missing port is informational, not a blocker
    assert check["ok"] is True
    probes = check.get("probes", [])
    assert any(pr.get("state") == "missing" for pr in probes), probes


def test_device_availability_detects_held_serial_port(tmp_path, home, monkeypatch):
    """When a serial port is held, the probe surfaces the holder + fix line."""
    p = tmp_path / "ROBOT.md"
    p.write_text("""\
---
rcan_version: "3.2"
metadata: { robot_name: bob, manufacturer: Acme, model: rx, firmware_version: 1.0.0 }
physics: { type: arm, dof: 6 }
drivers:
  - { id: arm, protocol: feetech, port: /dev/ttyTEST_FAKE }
capabilities: [arm.home]
safety:
  estop: { software: true, response_ms: 50 }
  max_joint_velocity_dps: 30
  hitl_gates: [{ scope: arm, require_auth: true }]
---
""")

    # Stub the probe to simulate a held port — avoids needing a real holder
    # and keeps the test deterministic across OS/lsof variants.
    from robot_md import compliance_status as cs

    def _fake_probe(port: str) -> dict:
        if port == "/dev/ttyTEST_FAKE":
            return {
                "state": "held",
                "holders": [{"pid": "12345", "command": "castor"}],
            }
        return {"state": "skipped", "reason": "not under test"}

    monkeypatch.setattr(cs, "_probe_serial_port_holder", _fake_probe)

    s = gather_status(p, network_probe=False)
    check = s["first_motion_readiness"]["checks"]["device_availability"]
    assert check["ok"] is False
    assert "castor" in check["detail"] and "12345" in check["detail"]
    assert "stop" in check["fix"].lower()
    # Bubbles into ranked blockers
    assert any("device_availability" in b for b in s["blockers"])


# ---- workspace_bounds_mm / kinematics / solver / joint_zero_sign (PR follow-up-2, 2026-04-25) ---


_MOTION_HEAD = """\
---
rcan_version: "3.2"
metadata: { robot_name: t, manufacturer: A, model: m, firmware_version: 1.0.0 }
"""
_MOTION_TAIL = """\
drivers:
  - { id: arm, protocol: feetech, port: /dev/null }
capabilities: [arm.home]
safety:
  estop: { software: true, response_ms: 50 }
  max_joint_velocity_dps: 30
  hitl_gates: [{ scope: arm, require_auth: true }]
---
"""


def _write(path, physics_yaml: str) -> None:
    path.write_text(_MOTION_HEAD + physics_yaml + _MOTION_TAIL)


def test_workspace_bounds_mm_flags_missing_bounds(tmp_path, home):
    """`calibrate --extrinsic` keys into physics.workspace.bounds_mm; missing
    it KeyErrors at calibration time. The pre-flight should refuse first."""
    p = tmp_path / "ROBOT.md"
    _write(p, "physics: { type: arm, dof: 2, workspace: { reach_mm: 400 } }\n")
    s = gather_status(p, network_probe=False)
    check = s["first_motion_readiness"]["checks"]["workspace_bounds_mm"]
    assert check["ok"] is False
    assert "bounds_mm" in check["detail"] and "bounds_mm" in check["fix"]


def test_kinematics_complete_flags_short_chain(tmp_path, home):
    """dof=6 but only 2 kinematics entries → IK + FK silently produce wrong
    answers. Pre-flight should refuse."""
    p = tmp_path / "ROBOT.md"
    _write(
        p,
        """physics:
  type: arm
  dof: 6
  workspace: { bounds_mm: { x: [0, 300], y: [-200, 200], z: [0, 250] } }
  solver: { ik_provider: stub }
  kinematics:
    - { id: j1, axis: z, limits_deg: [-180, 180], a_mm: 0, d_mm: 60, servo_id: 1, encoder_sign: 1, zero_pose_steps: 1500 }
    - { id: j2, axis: y, limits_deg: [-90, 90], a_mm: 100, d_mm: 0, servo_id: 2, encoder_sign: 1, zero_pose_steps: 2200 }
""",
    )
    s = gather_status(p, network_probe=False)
    check = s["first_motion_readiness"]["checks"]["kinematics_complete"]
    assert check["ok"] is False
    assert "2" in check["detail"] and "6" in check["detail"]


def test_solver_block_flags_missing_ik_provider(tmp_path, home):
    p = tmp_path / "ROBOT.md"
    _write(
        p,
        """physics:
  type: arm
  dof: 1
  workspace: { bounds_mm: { x: [0, 300], y: [-200, 200], z: [0, 250] } }
  kinematics:
    - { id: j1, axis: z, limits_deg: [-180, 180], a_mm: 0, d_mm: 60, servo_id: 1, encoder_sign: 1, zero_pose_steps: 1500 }
""",
    )
    s = gather_status(p, network_probe=False)
    check = s["first_motion_readiness"]["checks"]["solver_block"]
    assert check["ok"] is False
    assert "ik_provider" in check["detail"]


def test_joint_zero_sign_flags_default_zeros(tmp_path, home):
    """zero_pose_steps still at servo midpoint 2048 → calibration won't
    converge. Pre-flight should refuse to run --extrinsic."""
    p = tmp_path / "ROBOT.md"
    _write(
        p,
        """physics:
  type: arm
  dof: 1
  workspace: { bounds_mm: { x: [0, 300], y: [-200, 200], z: [0, 250] } }
  solver: { ik_provider: stub }
  kinematics:
    - { id: j1, axis: z, limits_deg: [-180, 180], a_mm: 0, d_mm: 60, servo_id: 1, encoder_sign: 1, zero_pose_steps: 2048 }
""",
    )
    s = gather_status(p, network_probe=False)
    check = s["first_motion_readiness"]["checks"]["joint_zero_sign"]
    assert check["ok"] is False
    assert "2048" in check["detail"] or "preset-default" in check["detail"]
    assert "calibrate --zero" in check["fix"]


def test_joint_zero_sign_clean_when_calibrated(tmp_path, home):
    """Non-2048 zero_pose_steps → operator has run --zero. Check passes."""
    p = tmp_path / "ROBOT.md"
    _write(
        p,
        """physics:
  type: arm
  dof: 1
  workspace: { bounds_mm: { x: [0, 300], y: [-200, 200], z: [0, 250] } }
  solver: { ik_provider: stub }
  kinematics:
    - { id: j1, axis: z, limits_deg: [-180, 180], a_mm: 0, d_mm: 60, servo_id: 1, encoder_sign: 1, zero_pose_steps: 1837 }
""",
    )
    s = gather_status(p, network_probe=False)
    assert s["first_motion_readiness"]["checks"]["joint_zero_sign"]["ok"] is True


# ---- Task 10: tri-state sig_state tests (TDD — must fail pre-1.2.4) ---------


def test_status_marks_artifact_invalid_when_signature_does_not_verify(manifest, home, tmp_path):
    """Structurally-signed but cryptographically-invalid artifact must report INVALID.

    Regression for the rcan-py 3.3.0 sign↔verify asymmetry: pre-1.2.4, this
    artifact would have been reported as `(signed)` and would have passed
    submission readiness, hiding a broken upstream signature.
    """
    # Provide an apikey so submission readiness evaluates the sig_state branch
    # (not the apikey-missing branch).
    apikey_path = home / ".robot-md" / "keys" / "RRN-000000000099.apikey"
    apikey_path.parent.mkdir(parents=True, exist_ok=True)
    apikey_path.write_text("dummy-apikey")

    artifacts_dir = tmp_path / "compliance"
    artifacts_dir.mkdir()
    bad_artifact = {
        "schema": "rcan-fria-v1",
        "generated_at": "2026-04-27T00:00:00Z",
        "system": {"rrn": "RRN-TEST"},
        "deployment": {},
        "conformance": {"score": 100, "pass_count": 5, "warn_count": 0, "fail_count": 0},
        "pq_signing_pub": "AAAA",  # valid b64, decodes to 3 bytes — fails ML-DSA verify
        "pq_kid": "deadbeef",
        "sig": {
            "ml_dsa": "AAAA",
            "ed25519": "AAAA",
            "ed25519_pub": "AAAA",
        },
    }
    (artifacts_dir / "fria.json").write_text(json.dumps(bad_artifact))

    status = gather_status(manifest, artifacts_dir=artifacts_dir, network_probe=False)
    fria = next(a for a in status["artifacts"]["present"] if a["schema"] == "rcan-fria-v1")
    assert fria["sig_state"] == "INVALID"
    assert status["submission_readiness"]["fria"]["ready"] is False
    assert "signature invalid" in status["submission_readiness"]["fria"]["reason"].lower()


def test_status_marks_artifact_verified_when_signature_is_valid(manifest, home, tmp_path):
    """A real signed artifact (top-level shape) reports `verified` and passes readiness."""
    from robot_md.signing import generate_keypair, save_keypair

    artifacts_dir = tmp_path / "compliance"
    artifacts_dir.mkdir()

    # Set up a valid signing keypair in the test home dir so apikey/signing checks pass.
    kp = generate_keypair()
    save_keypair("RRN-000000000099", kp)
    apikey_path = home / ".robot-md" / "keys" / "RRN-000000000099.apikey"
    apikey_path.write_text("dummy-apikey")

    # Sign a minimal IFU-shaped body and write it to the artifacts dir.
    from robot_md.signing import sign_body

    body = {"schema": "rcan-ifu-v1", "generated_at": "2026-04-27T00:00:00Z"}
    signed = sign_body(kp, body)
    (artifacts_dir / "ifu.json").write_text(json.dumps(signed))

    status = gather_status(manifest, artifacts_dir=artifacts_dir, network_probe=False)
    ifu = next(a for a in status["artifacts"]["present"] if a["schema"] == "rcan-ifu-v1")
    assert ifu["sig_state"] == "verified"
    assert status["submission_readiness"]["ifu"]["ready"] is True


def test_status_marks_artifact_unsigned_when_no_sig_field(manifest, home, tmp_path):
    """Artifact with neither top-level nor nested sig reports `unsigned`."""
    artifacts_dir = tmp_path / "compliance"
    artifacts_dir.mkdir()
    unsigned = {"schema": "rcan-fria-v1", "generated_at": "2026-04-27T00:00:00Z"}
    (artifacts_dir / "fria.json").write_text(json.dumps(unsigned))

    status = gather_status(manifest, artifacts_dir=artifacts_dir, network_probe=False)
    fria = next(a for a in status["artifacts"]["present"] if a["schema"] == "rcan-fria-v1")
    assert fria["sig_state"] == "unsigned"


# ---- Task 12: _render_sig_state helper test ---------------------------------


def test_render_sig_state_returns_correct_marker_and_suffix():
    from robot_md.compliance_status import _render_sig_state

    assert _render_sig_state("verified") == ("✓", "(signed, verified)")
    assert _render_sig_state("INVALID") == ("✗", "(signed, INVALID)")
    assert _render_sig_state("unsigned") == ("•", "(unsigned)")
