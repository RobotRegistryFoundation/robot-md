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


@pytest.fixture(autouse=True, scope="session")
def _bootstrap_scorers():
    """Force scorer self-registration once per session before any test runs."""
    from robot_md.spatial_eval.probe.scorer import _bootstrap

    _bootstrap()


@pytest.fixture
def reset_scorer_registry():
    """Snapshot _SCORERS before a test, restore after.

    Parity with reset_registry. Use when a test mutates _SCORERS (e.g., registers
    a deliberately-failing scorer to exercise runner error reporting). Module-level
    mutable state otherwise leaks across tests.
    """
    from robot_md.spatial_eval.probe.scorer import _SCORERS

    saved = _SCORERS.copy()
    yield _SCORERS
    _SCORERS.clear()
    _SCORERS.update(saved)
