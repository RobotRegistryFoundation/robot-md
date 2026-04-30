from __future__ import annotations

import pytest

pytestmark = pytest.mark.hardware


def test_replug_so_arm101_results_in_high_tier_auto_bind() -> None:
    """Run on bob with daemon active. Replug SO-ARM101. Within 1 s wall
    clock the manifest should gain a new drivers[] entry with backend:
    lerobot. Manual fixture — see cli/tests/manual/sphp_smoke.md."""
    pytest.skip("manual replug step required — see cli/tests/manual/sphp_smoke.md")
