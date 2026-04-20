"""Hardware tests — opt-in via RM_HARDWARE=1.

These tests require a real SO-ARM101 on /dev/ttyACM0 and a real OAK-D.
They are SKIPPED unconditionally in normal CI. Opt in with:

    RM_HARDWARE=1 pytest tests/hardware/ -v

The latch-recovery test is additionally gated behind RM_ALLOW_LATCH=1
because it intentionally trips the wrist_flex servo into overload
protection, which requires a physical power cycle to recover.
"""
from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RM_HARDWARE") == "1":
        return
    skip_hw = pytest.mark.skip(reason="hardware tests require RM_HARDWARE=1")
    for item in items:
        item.add_marker(skip_hw)
