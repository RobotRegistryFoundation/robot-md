"""Hardware smoke: reads factory cal from a connected OAK-D."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.hardware

pytest.importorskip("depthai")


def test_factory_cal_populates_rgb_intrinsic():
    from robot_md.autodetect import probe_depthai_cameras

    cams = probe_depthai_cameras()
    if not cams:
        pytest.skip("no depthai device connected")
    rgb = next((s for s in cams[0].streams if s.name == "rgb"), None)
    assert rgb is not None
    assert rgb.intrinsic is not None
    assert rgb.intrinsic["fx"] > 0
