from __future__ import annotations

from robot_md.spatial_eval.probe.datasets.loader import load_public_split


def test_loader_returns_probes_for_each_unit():
    by_unit = load_public_split()
    assert set(by_unit.keys()) == {"O1", "O2", "O3", "A1", "A2"}
    for unit, probes in by_unit.items():
        assert len(probes) >= 3
        for p in probes:
            assert p["unit"] == unit
            assert "ground_truth" in p
            assert "scenario_header" in p
