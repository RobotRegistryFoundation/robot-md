from __future__ import annotations
from robot_md.spatial_eval.probe.runner import run_probes
from robot_md.spatial_eval.probe.stacks import FakeStack


def _probe(pid: str, unit: str, scenario: str, question: dict, truth: dict) -> dict:
    return {"id": pid, "unit": unit, "scenario_header": scenario,
            "frames": [], "question": question, "ground_truth": truth}


def test_runner_side_by_side_with_delta():
    probes = [
        _probe("o1-1", "O1", "scene", {"type": "object_location"},
               {"still_present": True, "position": (0.0, 0.0, 0.0)}),
        _probe("o1-2", "O1", "scene", {"type": "object_location"},
               {"still_present": True, "position": (0.1, 0.0, 0.0)}),
    ]
    baseline = FakeStack({
        "o1-1": {"still_present": True, "position": [0.0, 0.0, 0.0]},
        "o1-2": {"still_present": True, "position": [0.1, 0.0, 0.0]},
    })
    declared = FakeStack({
        "o1-1": {"still_present": True, "position": [0.5, 0.5, 0.5]},  # bad
        "o1-2": {"still_present": True, "position": [0.1, 0.0, 0.0]},  # good
    })
    result = run_probes(probes, baseline=baseline, declared=declared)
    assert result.baseline_per_unit["O1"].passed == 2
    assert result.declared_per_unit["O1"].passed == 1
    assert result.delta_per_unit["O1"] == result.declared_per_unit["O1"].score - result.baseline_per_unit["O1"].score
