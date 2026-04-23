"""v0.9.3 — safety benchmarks module tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ruamel.yaml")

from robot_md.benchmarks import (
    BENCHMARK_SCHEMA_NAME,
    DEFAULT_ITERATIONS,
    DEFAULT_THRESHOLDS_MS,
    PATHS,
    PathStats,
    _inject_bench_skill,
    _stats,
    build_artifact,
    resolve_thresholds,
    run_bounds_check,
    run_confidence_gate,
    run_estop,
    run_full_pipeline,
    sign_artifact,
)
from robot_md.parser import parse_file
from robot_md.robot_spec import RobotSpec

BOB_MIN = """\
---
rcan_version: "3.0"
metadata:
  robot_name: bench-bot
  manufacturer: acme
  model: b1
  firmware_version: 1.0.0
physics:
  type: arm
  dof: 6
  workspace:
    bounds_mm:
      x: [0, 500]
      y: [-250, 250]
      z: [0, 300]
drivers:
  - { id: arm, protocol: feetech, port: /dev/ttyACM0 }
safety:
  estop: { software: true, response_ms: 100 }
---
# bench-bot
"""


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "bench.ROBOT.md"
    p.write_text(BOB_MIN)
    return p


def _spec(tmp_path: Path) -> RobotSpec:
    return RobotSpec.from_parsed(parse_file(_write(tmp_path)))


# ---- _stats -------------------------------------------------------------


def test_stats_computes_percentiles_and_pass():
    samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    s = _stats(samples, threshold_ms=10.0)
    assert s.min_ms == 1.0
    assert s.max_ms == 10.0
    assert 5.0 <= s.mean_ms <= 6.0
    # nearest-rank p95 on 10 samples lands on the 10th (max)
    assert s.p95_ms == 10.0
    assert s.passed is True


def test_stats_pass_false_when_p95_exceeds_threshold():
    s = _stats([100.0] * 20, threshold_ms=50.0)
    assert s.passed is False


def test_path_stats_as_dict_rounds_and_renames_pass():
    ps = PathStats(min_ms=0.123467, mean_ms=0.6, p95_ms=1.2, p99_ms=1.4, max_ms=2.0, passed=True)
    d = ps.as_dict()
    assert d["pass"] is True
    assert "passed" not in d
    assert d["min_ms"] == 0.1235  # rounded to 4 places (0.123467 → 0.1235)


# ---- individual path runners -------------------------------------------


def test_run_estop_returns_iter_samples():
    samples = run_estop(iterations=5)
    assert len(samples) == 5
    assert all(s >= 0 for s in samples)


def test_run_bounds_check_uses_workspace_declared(tmp_path):
    spec = _spec(tmp_path)
    samples = run_bounds_check(iterations=3, spec=spec)
    assert len(samples) == 3


def test_run_confidence_gate_uses_injected_skill(tmp_path):
    spec = _spec(tmp_path)
    shim = _inject_bench_skill(spec)
    assert any(s.id == "_bench_skill" for s in shim.learned_skills)
    samples = run_confidence_gate(iterations=3, spec=shim)
    assert len(samples) == 3


def test_run_full_pipeline_end_to_end(tmp_path):
    path = _write(tmp_path)
    samples = run_full_pipeline(iterations=2, manifest_path=path)
    assert len(samples) == 2


# ---- threshold resolution ----------------------------------------------


def test_resolve_thresholds_pulls_estop_from_manifest(tmp_path):
    spec = _spec(tmp_path)
    t = resolve_thresholds(spec)
    # Manifest says response_ms: 100, which matches the default — either way,
    # the key must be present and numeric.
    assert t["estop"] == 100.0
    assert t["bounds_check"] == DEFAULT_THRESHOLDS_MS["bounds_check"]
    assert t["confidence_gate"] == DEFAULT_THRESHOLDS_MS["confidence_gate"]
    assert t["full_pipeline"] == DEFAULT_THRESHOLDS_MS["full_pipeline"]


# ---- build_artifact shape ---------------------------------------------


def test_build_artifact_schema_and_shape(tmp_path):
    path = _write(tmp_path)
    art = build_artifact(path, iterations=3)
    assert art["schema"] == BENCHMARK_SCHEMA_NAME
    assert art["mode"] == "synthetic"
    assert art["iterations"] == 3
    assert set(art["thresholds"].keys()) == {f"{p}_p95_ms" for p in PATHS}
    assert set(art["results"].keys()) == set(PATHS)
    for p in PATHS:
        r = art["results"][p]
        assert {"min_ms", "mean_ms", "p95_ms", "p99_ms", "max_ms", "pass"} <= r.keys()
    assert isinstance(art["overall_pass"], bool)
    # generated_at is a UTC ISO string ending in Z
    assert art["generated_at"].endswith("Z")


def test_build_artifact_default_iterations(tmp_path):
    path = _write(tmp_path)
    art = build_artifact(path)
    assert art["iterations"] == DEFAULT_ITERATIONS


def test_build_artifact_overall_pass_reflects_individual(tmp_path):
    path = _write(tmp_path)
    art = build_artifact(path, iterations=2)
    individual = [art["results"][p]["pass"] for p in PATHS]
    assert art["overall_pass"] == all(individual)


# ---- sign integration (v0.9.1) -----------------------------------------


def test_sign_artifact_raises_when_no_keypair(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(RuntimeError, match="no signing keypair"):
        sign_artifact({"hello": "world"}, rrn="RRN-000000000099")


def test_sign_artifact_appends_sig_block(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from robot_md.signing import generate_keypair, save_keypair, verify_body

    save_keypair("RRN-000000000099", generate_keypair())
    art = {"schema": BENCHMARK_SCHEMA_NAME, "overall_pass": True}
    signed = sign_artifact(art, rrn="RRN-000000000099")
    assert "sig" in signed
    assert "pq_signing_pub" in signed
    assert "pq_kid" in signed
    assert verify_body(signed) is True


def test_full_artifact_roundtrip_signs_and_verifies(tmp_path, monkeypatch):
    """build_artifact → sign_artifact → verify_body holds end-to-end."""
    monkeypatch.setenv("HOME", str(tmp_path))
    from robot_md.signing import generate_keypair, save_keypair, verify_body

    save_keypair("RRN-000000000099", generate_keypair())
    path = _write(tmp_path)
    art = build_artifact(path, iterations=2)
    signed = sign_artifact(art, rrn="RRN-000000000099")
    # Artifact must round-trip through JSON (canonical_json only accepts
    # JSON-serializable values) and verify.
    _ = json.dumps(signed, sort_keys=True)
    assert verify_body(signed) is True
