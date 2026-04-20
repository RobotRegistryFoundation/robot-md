"""arm.pick("red_lego") with a bogus 8m-wall red pixel in the RGB frame —
the depth filter introduced in v0.7 Task 4/5 must reject the wall pixel
and target the tabletop LEGO.

Dispatch shape: perception.vision_find("red_lego") directly. This is the
integration point that exercises HSV detector + workspace-auto-derived depth
bounds end-to-end without needing the full capability machinery.

Scene:
  - RGB: two red blobs of equal size (30x30 px, both pass min_area=500)
      tabletop blob: center (300, 200)
      wall blob:     center (100, 100)
  - Depth: tabletop patch at 450mm (inside auto-derived bounds 44-612mm),
           everywhere else at 8000mm (far outside bounds)
  - Extrinsic + workspace from so-arm101 preset defaults.

Without depth filtering both blobs are visible (same HSV signature, same
area). With depth filtering the wall blob is masked to zero and only the
tabletop centroid survives.
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.mark.integration
def test_arm_pick_depth_filtered_ignores_8m_wall(tmp_path):
    """RGB frame has TWO equal-size red blobs: one at tabletop depth (450mm),
    one at 8m (simulated wall). Without depth filtering either blob could win.
    With the v0.7 workspace-bounds depth filter, only the tabletop survives.
    """
    # ------------------------------------------------------------------ #
    # 1. Build a real RobotSpec from the so-arm101 preset.                #
    #    This gives us red_lego descriptor, workspace bounds, and the     #
    #    default extrinsic — exactly what the auto-derive path needs.     #
    # ------------------------------------------------------------------ #
    from robot_md.init import default_flow
    from robot_md.init_phases import PhaseResult
    from robot_md.mcp.context import load_context
    from robot_md.robot_spec import RobotSpec
    from robot_md.parser import parse_file

    out = tmp_path / "ROBOT.md"

    def _stub_phase(name):
        def _inner(*a, **kw):
            return PhaseResult(phase=name, status="skipped", message="", detail={})
        return _inner

    with patch("robot_md.init.phase_register", _stub_phase("register")), \
         patch("robot_md.init.phase_install_mcp", _stub_phase("install_mcp")), \
         patch("robot_md.init.phase_install_skill", _stub_phase("install_skill")), \
         patch("robot_md.init.phase_calibrate_sign", _stub_phase("calibrate_sign")), \
         patch("robot_md.init.phase_calibrate_zero", _stub_phase("calibrate_zero")), \
         patch("robot_md.init.phase_teach_poses", _stub_phase("teach_poses")):
        rc = default_flow(
            out, robot_name="depth-test-bot", preset_name="so-arm101",
            do_install_mcp=False, do_install_skill=False,
            do_register=False, do_refresh_claude_md=False,
        )
    assert rc == 0, f"init failed rc={rc}"

    parsed = parse_file(out)
    spec = RobotSpec.from_parsed(parsed)
    assert spec is not None

    # Sanity: spec has the red_lego descriptor registered.
    descr = spec.vision.find("red_lego")
    assert descr is not None, "red_lego descriptor not found in spec"

    # Sanity: spec has workspace + extrinsic so auto-derive can fire.
    cam0 = spec.physics.cameras[0]
    assert cam0.extrinsic is not None, "no extrinsic in spec"
    assert spec.physics.workspace is not None, "no workspace in spec"

    # ------------------------------------------------------------------ #
    # 2. Build synthetic scene.                                            #
    #                                                                      #
    #    Both blobs are 30x30 px (area=900, both pass min_area=500)       #
    #    so blob size is NOT the discriminator — depth is.                 #
    #    HSV params: h_ranges [[0,10],[170,180]], s_min=110, v_min=80.    #
    #    BGR (0,0,220) → HSV (0, 255, 220) → passes both h-ranges.       #
    # ------------------------------------------------------------------ #
    TABLETOP_DEPTH_MM = 450   # inside auto-derived bounds (~45–612 mm)
    WALL_DEPTH_MM     = 8000  # far outside bounds

    rgb = np.zeros((400, 600, 3), dtype=np.uint8)
    # Tabletop LEGO blob — center (300, 200).
    rgb[185:215, 285:315, 2] = 220
    # Wall red blob — center (100, 100), same size so not discriminated by area.
    rgb[85:115, 85:115, 2] = 220

    depth = np.full((400, 600), WALL_DEPTH_MM, dtype=np.uint16)
    depth[185:215, 285:315] = TABLETOP_DEPTH_MM  # only the tabletop patch is close

    # Intrinsic matrix (simple pinhole, cx=300 cy=200 so tabletop center
    # projects to the optical center when depth is queried).
    K = np.array([[600., 0., 300.], [0., 600., 200.], [0., 0., 1.]])

    # ------------------------------------------------------------------ #
    # 3. Instantiate real Perception, stub only grab_frame.               #
    # ------------------------------------------------------------------ #
    from robot_md.backends.feetech_depthai.perception import Perception

    # Perception is a dataclass; driver_id is the only required field.
    # We stub grab_frame after construction so no real hardware is touched.
    per = Perception(driver_id="oak-d-test", _spec=spec)
    per.grab_frame = MagicMock(return_value=(rgb, depth, K))

    # ------------------------------------------------------------------ #
    # 4. Run the real vision_find pipeline.                               #
    # ------------------------------------------------------------------ #
    result = per.vision_find(descriptor="red_lego", spec=spec)

    # ------------------------------------------------------------------ #
    # 5. Assert: depth filter chose the tabletop blob, not the wall blob. #
    # ------------------------------------------------------------------ #
    assert result.get("status") == "ok", (
        f"vision_find returned status={result.get('status')!r}, "
        f"reason={result.get('reason')!r}. "
        "Expected 'ok' — depth-filtered tabletop blob should be found."
    )

    px, py = result["pixel"]
    # Tabletop blob occupies x in [285,315), y in [185,215).
    # Wall blob occupies x in [85,115), y in [85,115).
    assert 285 <= px <= 315 and 185 <= py <= 215, (
        f"Centroid ({px}, {py}) does not land in the tabletop blob region "
        f"(x 285-315, y 185-215). If it landed near (100, 100) the wall pixel "
        "was chosen despite the depth filter — depth filtering is broken."
    )

    # Also assert the reported depth is the tabletop depth, not 8m.
    depth_reported = result["depth_mm"]
    assert depth_reported < 1000, (
        f"Reported depth {depth_reported:.0f}mm looks like wall depth ({WALL_DEPTH_MM}mm), "
        "not tabletop depth ({TABLETOP_DEPTH_MM}mm)."
    )

    # Confirm auto-derive fired: if ignore_workspace_bounds were set or
    # manual bounds were present, the test would still pass but for the
    # wrong reason. Verify the descriptor params did NOT have manual bounds.
    assert descr.params.get("min_depth_mm") is None, (
        "red_lego descriptor has manual min_depth_mm — auto-derive path not exercised."
    )
    assert descr.params.get("max_depth_mm") is None, (
        "red_lego descriptor has manual max_depth_mm — auto-derive path not exercised."
    )
