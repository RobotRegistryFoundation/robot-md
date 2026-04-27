from __future__ import annotations

# Eager imports so units self-register on package import. Mirrors the
# probe/scorers package; ensures REGISTRY is populated for any consumer
# (tests, runner, MCP tools) without relying on a conftest bootstrap.
from robot_md.spatial_eval.units import (
    a1_grasp,  # noqa: F401
    a2_stability,  # noqa: F401
    o1_permanence,  # noqa: F401
    o2_container,  # noqa: F401
    o3_partial_view,  # noqa: F401
)
from robot_md.spatial_eval.units.base import REGISTRY, get_unit, register

__all__ = ["REGISTRY", "get_unit", "register"]
