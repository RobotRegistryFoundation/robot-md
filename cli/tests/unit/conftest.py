"""Unit-test conftest: disable dashboard publisher by default.

Existing unit tests call load_context() without a tmp HOME, which would cause
the publisher to write events.jsonl into the real ~/.robot-md/.  This autouse
fixture suppresses that for every unit test.  Tests that deliberately exercise
publisher wiring (test_dashboard_context_wiring.py) override this env var via
their own monkeypatch.setenv / monkeypatch.delenv calls.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_dashboard_publisher(monkeypatch):
    """Prevent load_context from starting a publisher in unit tests by default."""
    monkeypatch.setenv("ROBOT_MD_DASHBOARD_DISABLED", "1")
