from __future__ import annotations

import pytest

from robot_md.spatial_eval.units.base import REGISTRY


@pytest.fixture
def reset_registry():
    """Snapshot REGISTRY before a test, restore after.

    Use when a test mutates REGISTRY (e.g., registers a fake unit). Without
    this fixture, mutations bleed across tests because REGISTRY is module-level
    state.
    """
    saved = REGISTRY.copy()
    yield REGISTRY
    REGISTRY.clear()
    REGISTRY.update(saved)
