from __future__ import annotations

import pytest

pytestmark = pytest.mark.hardware


def test_unknown_vid_pid_lands_as_low_tier() -> None:
    """Plug a device whose VID:PID isn't in the curated table. Expect a
    queue record at tier=LOW with `no preset match` reason. Manual fixture
    — see cli/tests/manual/sphp_smoke.md."""
    pytest.skip("manual plug step required — see cli/tests/manual/sphp_smoke.md")
