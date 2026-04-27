from __future__ import annotations

import pytest

from robot_md.spatial_eval.units import REGISTRY, get_unit
from robot_md.spatial_eval.units.base import ProbeAnswer, Unit  # noqa: F401


def test_registry_lists_all_five_v1_units():
    # Force import of all five so they self-register.
    import robot_md.spatial_eval.units.a1_grasp
    import robot_md.spatial_eval.units.a2_stability
    import robot_md.spatial_eval.units.o1_permanence
    import robot_md.spatial_eval.units.o2_container
    import robot_md.spatial_eval.units.o3_partial_view  # noqa: F401

    assert sorted(REGISTRY.keys()) == ["A1", "A2", "O1", "O2", "O3"]


def test_get_unit_raises_on_unknown():
    with pytest.raises(KeyError):
        get_unit("Z9")
