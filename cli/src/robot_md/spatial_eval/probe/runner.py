from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from robot_md.spatial_eval.probe.scorer import score_answer
from robot_md.spatial_eval.probe.stacks import Stack
from robot_md.spatial_eval.score import PerUnitProbeScore
from robot_md.spatial_eval.units import get_unit


@dataclass(frozen=True)
class ProbeRunResult:
    baseline_per_unit: dict[str, PerUnitProbeScore]
    declared_per_unit: dict[str, PerUnitProbeScore]
    delta_per_unit: dict[str, float]
    per_probe: list[dict]  # raw per-probe records for evidence packet


def _score_one(unit: str, raw_answer: dict, truth: dict) -> tuple[bool, float]:
    parsed = get_unit(unit).parse_answer(raw_answer)
    return score_answer(unit, parsed, truth)


def run_probes(
    probes: Iterable[dict],
    *,
    baseline: Stack,
    declared: Stack | None = None,
    progress_cb=None,
) -> ProbeRunResult:
    by_unit_baseline: dict[str, list[tuple[bool, float]]] = defaultdict(list)
    by_unit_declared: dict[str, list[tuple[bool, float]]] = defaultdict(list)
    per_probe: list[dict] = []
    probes_list = list(probes)
    total = len(probes_list)
    for i, p in enumerate(probes_list):
        unit = p["unit"]
        truth = p["ground_truth"]
        # Errors propagate; the MCP tool wrapper (T25) is responsible for
        # converting per-probe failures into structured Score JSON entries.
        b_raw = baseline.answer(p)
        b_pass, b_score = _score_one(unit, b_raw, truth)
        by_unit_baseline[unit].append((b_pass, b_score))

        d_pass, d_score = (b_pass, b_score)
        d_raw = b_raw
        if declared is not None and declared is not baseline:
            d_raw = declared.answer(p)
            d_pass, d_score = _score_one(unit, d_raw, truth)
        by_unit_declared[unit].append((d_pass, d_score))

        per_probe.append({
            "id": p["id"], "unit": unit,
            "baseline": {"answer": b_raw, "passed": b_pass, "score": b_score},
            "declared": {"answer": d_raw, "passed": d_pass, "score": d_score},
        })
        if progress_cb is not None:
            progress_cb(i + 1, total, unit)

    def _aggregate(by_unit: dict[str, list[tuple[bool, float]]]) -> dict[str, PerUnitProbeScore]:
        out: dict[str, PerUnitProbeScore] = {}
        for unit, rows in by_unit.items():
            n = len(rows)
            passed = sum(1 for ok, _ in rows if ok)
            score = sum(s for _, s in rows) / max(1, n)
            out[unit] = PerUnitProbeScore(score=score, n=n, passed=passed)
        return out

    base = _aggregate(by_unit_baseline)
    decl = _aggregate(by_unit_declared)
    delta = {u: decl[u].score - base[u].score for u in base}
    return ProbeRunResult(
        baseline_per_unit=base,
        declared_per_unit=decl,
        delta_per_unit=delta,
        per_probe=per_probe,
    )
