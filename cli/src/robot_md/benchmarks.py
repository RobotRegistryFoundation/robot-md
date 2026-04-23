"""§23 safety benchmarks for robot-md's own safety-critical paths.

Measures the four canonical paths declared in rcan-spec §23 — estop,
bounds_check, confidence_gate, full_pipeline — in synthetic mode,
purely in-process. No hardware, no MCP subprocess, no castor.

Path mapping (robot-md's safety code, not castor's):
- estop            → EstopFlag.set()/is_set()/clear() cycle
- bounds_check     → preconditions._check_one(workspace_declared, ...)
- confidence_gate  → preconditions._check_one(learned_skill_ok, ...)
- full_pipeline    → parse_file + validate + RobotSpec.from_parsed +
                     preconditions.evaluate over a multi-precondition
                     CapabilityContract

Threshold resolution:
- estop ← manifest safety.estop.response_ms (schema-validated int ms)
- others ← rcan-spec §23 example defaults (5, 2, 50 ms)

Emission shape matches rcan-spec §23 rcan-safety-benchmark-v1 exactly.
When --sign is passed, the artifact is routed through v0.9.1 sign_body
so the signed blob is wire-compatible with signing.verify_body().
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from rcan import build_safety_benchmark
from rcan.compliance import SAFETY_BENCHMARK_SCHEMA as BENCHMARK_SCHEMA_NAME  # noqa: F401

from robot_md.mcp.context import EstopFlag
from robot_md.parser import parse_file
from robot_md.preconditions import _check_one, evaluate
from robot_md.robot_spec import CapabilityContract, Precondition, RobotSpec
from robot_md.validate import validate as validate_parsed

PATHS = ("estop", "bounds_check", "confidence_gate", "full_pipeline")
DEFAULT_ITERATIONS = 20
DEFAULT_THRESHOLDS_MS: dict[str, float] = {
    "estop": 100.0,
    "bounds_check": 5.0,
    "confidence_gate": 2.0,
    "full_pipeline": 50.0,
}


@dataclass(frozen=True)
class PathStats:
    min_ms: float
    mean_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    passed: bool

    def as_dict(self) -> dict:
        return {
            "min_ms": round(self.min_ms, 4),
            "mean_ms": round(self.mean_ms, 4),
            "p95_ms": round(self.p95_ms, 4),
            "p99_ms": round(self.p99_ms, 4),
            "max_ms": round(self.max_ms, 4),
            "pass": self.passed,
        }


def _time(fn: Callable[[], Any], iters: int) -> list[float]:
    """Return per-call wall-clock latencies in milliseconds."""
    samples: list[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return samples


def _stats(samples: list[float], threshold_ms: float) -> PathStats:
    """Nearest-rank percentile — no scipy, works on small N."""
    n = len(samples)
    srt = sorted(samples)

    def pct(p: float) -> float:
        k = max(0, min(n - 1, round(p / 100.0 * (n - 1))))
        return srt[k]

    return PathStats(
        min_ms=srt[0],
        mean_ms=statistics.mean(samples),
        p95_ms=pct(95),
        p99_ms=pct(99),
        max_ms=srt[-1],
        passed=pct(95) <= threshold_ms,
    )


def run_estop(iterations: int) -> list[float]:
    """Time set → is_set → clear on a fresh EstopFlag per iteration."""
    flag = EstopFlag()

    def one() -> None:
        flag.set()
        flag.is_set()
        flag.clear()

    return _time(one, iterations)


def run_bounds_check(iterations: int, spec: Any) -> list[float]:
    """Time a workspace_declared precondition check (robot-md's bounds proxy).

    `_check_one` for `workspace_declared` reads spec.physics.workspace and
    returns None (pass) or PreconditionFailure. Measures the dispatch +
    attribute walk cost on the happy-path.
    """
    p = Precondition(kind="workspace_declared", name=None, detail={})

    def one() -> None:
        _check_one(p, spec, backend_resolved=True)

    return _time(one, iterations)


def run_confidence_gate(iterations: int, spec: Any) -> list[float]:
    """Time a learned_skill_ok precondition check — robot-md's confidence gate.

    `_check_one` walks spec.learned_skills for the named id and verifies
    status == "ok". The spec passed in must carry a skill id "_bench_skill"
    with status "ok" so we measure the success branch.
    """
    p = Precondition(kind="learned_skill_ok", name="_bench_skill", detail={})

    def one() -> None:
        _check_one(p, spec, backend_resolved=True)

    return _time(one, iterations)


def run_full_pipeline(iterations: int, manifest_path: Path) -> list[float]:
    """Time parse + validate + RobotSpec.from_parsed + multi-precondition eval.

    Mirrors the command-dispatch safety chain: read the manifest, confirm
    it's schema-valid, materialize the spec, evaluate all preconditions
    in a mocked capability contract. This is the full safety decision
    latency for a fresh invocation.
    """
    contract = CapabilityContract(
        preconditions=(
            Precondition(kind="workspace_declared", name=None, detail={}),
            Precondition(kind="backend_resolved", name=None, detail={}),
        )
    )

    def one() -> None:
        parsed = parse_file(manifest_path)
        validate_parsed(parsed)
        spec = RobotSpec.from_parsed(parsed)
        evaluate(contract, spec, backend_resolved=True)

    return _time(one, iterations)


def _inject_bench_skill(spec: RobotSpec) -> Any:
    """Return a minimal spec shim carrying a _bench_skill with status='ok'.

    The precondition code accesses `spec.learned_skills` via getattr — any
    attribute-bearing object works. SimpleNamespace is the cleanest shim
    that preserves the original spec's other fields we might read.
    """
    bench_skill = SimpleNamespace(id="_bench_skill", status="ok")
    return SimpleNamespace(
        physics=spec.physics,
        safety=spec.safety,
        learned_skills=(*spec.learned_skills, bench_skill),
    )


def resolve_thresholds(spec: RobotSpec) -> dict[str, float]:
    """Layer: §23 defaults ← manifest safety.estop.response_ms (estop only)."""
    t = dict(DEFAULT_THRESHOLDS_MS)
    if spec.safety is not None and spec.safety.estop_response_ms:
        t["estop"] = float(spec.safety.estop_response_ms)
    return t


def build_artifact(
    manifest_path: Path,
    *,
    iterations: int = DEFAULT_ITERATIONS,
) -> dict:
    """Run all four synthetic benchmarks, assemble the §23 artifact dict."""
    parsed = parse_file(manifest_path)
    spec = RobotSpec.from_parsed(parsed)
    thresholds = resolve_thresholds(spec)

    samples = {
        "estop": run_estop(iterations),
        "bounds_check": run_bounds_check(iterations, spec),
        "confidence_gate": run_confidence_gate(iterations, _inject_bench_skill(spec)),
        "full_pipeline": run_full_pipeline(iterations, manifest_path),
    }
    results = {path: _stats(samples[path], thresholds[path]).as_dict() for path in PATHS}
    overall_pass = all(r["pass"] for r in results.values())

    return build_safety_benchmark(
        iterations=iterations,
        thresholds={f"{p}_p95_ms": thresholds[p] for p in PATHS},
        results=results,
        mode="synthetic",
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        overall_pass=overall_pass,
    )


def sign_artifact(artifact: dict, rrn: str) -> dict:
    """Sign the artifact with the v0.9.1 hybrid keypair for `rrn`.

    Raises RuntimeError if the keystore has no signing key for `rrn` —
    the operator must have run `robot-md register` first.
    Returns a new dict; the input is not mutated. Wire format matches
    signing.verify_body (sig block + pq_signing_pub + pq_kid appended to
    a canonical JSON of the artifact).
    """
    from robot_md.signing import load_keypair, sign_body

    kp = load_keypair(rrn)
    if kp is None:
        raise RuntimeError(
            f"no signing keypair for {rrn} at ~/.robot-md/keys/. "
            f"Run `robot-md register <manifest>` to mint one."
        )
    return sign_body(kp, artifact)
