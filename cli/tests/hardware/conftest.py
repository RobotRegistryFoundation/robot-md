"""Hardware tests — opt-in via RM_HARDWARE=1 or --run-hardware.

These tests require a real SO-ARM101 on /dev/ttyACM0 and a real OAK-D.
They are SKIPPED unconditionally in normal CI. Opt in with:

    RM_HARDWARE=1 pytest tests/hardware/ -v

The latch-recovery test is additionally gated behind RM_ALLOW_LATCH=1
because it intentionally trips the wrist_flex servo into overload
protection, which requires a physical power cycle to recover.

Skip wiring lives in the root tests/conftest.py — it filters by the
@pytest.mark.hardware marker. This file is intentionally a marker-only
stub so plugin discovery still treats tests/hardware/ as a package.
"""

from __future__ import annotations
