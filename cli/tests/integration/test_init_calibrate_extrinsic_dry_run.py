"""Full phase_calibrate_extrinsic sweep with a synthetic camera + bus that
simulates a ground-truth extrinsic. The manifest must end with
extrinsic_source=gripper_silhouette_calibrated and a small residual.

This is a pure-Python integration test — no real hardware, no DepthAI
pipeline. The camera stub generates depth frames where the gripper
appears at the correct pixel given a known GT extrinsic.

Design notes
------------
* GT extrinsic = preset default + small translation offset (+15 mm tx,
  +10 mm tz). Small enough that the preset-default search window
  (search_radius_mm=60) still catches the blob; large enough that
  solve() has real work to do.
* Depth frames use uint16 mm values. find_in_depth reads depth as float mm.
* The synthetic bus updates `current` in-place on each interpolate call
  so Kinematics.fk() and the phase's read_positions() agree.
* phase_calibrate_extrinsic is patched out inside default_flow (it would
  skip anyway because stdin.isatty() is False in pytest, but patching
  makes intent explicit). We then invoke it directly with our mocks.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.mark.integration
def test_full_sweep_produces_calibrated_manifest(tmp_path, monkeypatch):
    from robot_md.init import default_flow
    from robot_md.init_phases import PhaseResult
    from robot_md.init_phases.calibrate_extrinsic import phase_calibrate_extrinsic
    from robot_md.parser import parse_file
    from robot_md.kinematics import Kinematics
    from robot_md.extrinsic import six_vec_to_matrix

    # ------------------------------------------------------------------
    # 1. Seed a manifest from the so-arm101 preset. Patch out all phases
    #    we don't care about (same pattern as test_arm_pick_depth_filtered).
    # ------------------------------------------------------------------
    manifest = tmp_path / "ROBOT.md"

    def _stub_phase(name):
        def _inner(*a, **kw):
            return PhaseResult(phase=name, status="skipped", message="", detail={})
        return _inner

    with (
        patch("robot_md.init.phase_register", _stub_phase("register")),
        patch("robot_md.init.phase_install_mcp", _stub_phase("install_mcp")),
        patch("robot_md.init.phase_install_skill", _stub_phase("install_skill")),
        patch("robot_md.init.phase_calibrate_sign", _stub_phase("calibrate_sign")),
        patch("robot_md.init.phase_calibrate_zero", _stub_phase("calibrate_zero")),
        patch("robot_md.init.phase_calibrate_extrinsic", _stub_phase("calibrate_extrinsic")),
        patch("robot_md.init.phase_teach_poses", _stub_phase("teach_poses")),
        patch("robot_md.init._refresh_claude_md"),
    ):
        rc = default_flow(
            manifest,
            robot_name="extrinsic-test-bot",
            preset_name="so-arm101",
            do_register=False,
            do_install_mcp=False,
            do_install_skill=False,
            do_refresh_claude_md=False,
        )
    assert rc == 0, f"default_flow failed rc={rc}"
    assert manifest.exists(), "manifest was not written"

    # Confirm the preset-default extrinsic is present.
    fm = parse_file(manifest).frontmatter
    cam0 = fm["physics"]["solver"]["cameras"][0]
    assert cam0.get("extrinsic_source") == "preset_default", (
        f"expected preset_default, got {cam0.get('extrinsic_source')!r}"
    )
    preset_6vec = list(cam0["extrinsic"])

    # ------------------------------------------------------------------
    # 2. Ground-truth extrinsic: preset + a small offset so solve() has
    #    real work and can't just return the initial guess.
    #    Offset: +15mm tx, +10mm tz. Well within search_radius_mm=60.
    # ------------------------------------------------------------------
    gt_6vec = [preset_6vec[0] + 15.0,  # tx
               preset_6vec[1],          # ty
               preset_6vec[2] + 10.0,  # tz
               preset_6vec[3],          # rx
               preset_6vec[4],          # ry
               preset_6vec[5]]          # rz
    T_gt = six_vec_to_matrix(gt_6vec)   # camera→base
    T_gt_inv = np.linalg.inv(T_gt)      # base→camera

    # Wide-angle intrinsics so all 6 sweep poses land inside the frame.
    # With fx=fy=200 the horizontal FOV is ~72° and vertical ~76°, which
    # captures the full so-arm101 workspace as seen from the preset extrinsic.
    K = np.array([[200.0, 0.0, 320.0],
                  [0.0,   200.0, 400.0],
                  [0.0,   0.0,   1.0]])
    HEIGHT, WIDTH = 800, 640

    # ------------------------------------------------------------------
    # 3. Synthetic servo bus: steps dict updated on each interpolate call.
    # ------------------------------------------------------------------
    kin = Kinematics(fm)
    current: dict[str, int] = {j.id: j.rad_to_steps(0.0) for j in kin.joints}

    bus = MagicMock()
    bus.read_positions.side_effect = lambda: dict(current)

    def _interp(_from, to_dict, **_kw):
        current.update(to_dict)
    bus.interpolate.side_effect = _interp

    # ------------------------------------------------------------------
    # 4. Synthetic camera: project GT-extrinsic FK tip into depth frame.
    # ------------------------------------------------------------------
    def _grab_frame():
        """Compute FK from current step positions, project through GT T_gt_inv."""
        rad_cfg: dict[str, float] = {
            j.id: j.steps_to_rad(current.get(j.id, j.zero_pose_steps))
            for j in kin.joints
        }
        tip_base = np.array(kin.fk(rad_cfg), dtype=float)  # (x, y, z) mm
        tip_cam_h = T_gt_inv @ np.append(tip_base, 1.0)    # (4,)
        tip_cam = tip_cam_h[:3]                              # (x, y, z) mm

        depth = np.zeros((HEIGHT, WIDTH), dtype=np.uint16)
        if tip_cam[2] <= 0:
            # Gripper behind camera — return empty frame (pose will be skipped).
            return None, depth, K

        u = int(round(K[0, 0] * tip_cam[0] / tip_cam[2] + K[0, 2]))
        v = int(round(K[1, 1] * tip_cam[1] / tip_cam[2] + K[1, 2]))

        if 0 <= u < WIDTH and 0 <= v < HEIGHT:
            yy, xx = np.ogrid[:HEIGHT, :WIDTH]
            # Radius 8px gives >50 pixels — well above the 5-point threshold.
            mask = np.hypot(xx - u, yy - v) <= 8
            depth[mask] = int(round(tip_cam[2]))

        rgb = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        return rgb, depth, K

    camera = MagicMock()
    camera.grab_frame.side_effect = _grab_frame

    # ------------------------------------------------------------------
    # 5. Patch builtins.input so the "proceed?" prompt auto-accepts.
    # ------------------------------------------------------------------
    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

    # ------------------------------------------------------------------
    # 6. Invoke phase_calibrate_extrinsic directly with our mocks.
    # ------------------------------------------------------------------
    result = phase_calibrate_extrinsic(
        manifest,
        bus=bus,
        camera=camera,
        interactive=True,
        n_poses=6,
    )

    assert result.status == "ok", (
        f"expected ok, got {result.status!r}: {result.message}"
    )
    assert "residual_mm" in result.detail, "residual_mm not in result.detail"
    assert result.detail["residual_mm"] < 15.0, (
        f"residual {result.detail['residual_mm']:.2f}mm exceeds 15mm threshold"
    )

    # ------------------------------------------------------------------
    # 7. Verify the manifest was updated correctly.
    # ------------------------------------------------------------------
    post = parse_file(manifest).frontmatter
    post_cam0 = post["physics"]["solver"]["cameras"][0]

    assert post_cam0.get("extrinsic_source") == "gripper_silhouette_calibrated", (
        f"expected gripper_silhouette_calibrated, got {post_cam0.get('extrinsic_source')!r}"
    )
    assert "extrinsic_residual_mm" in post_cam0, (
        "extrinsic_residual_mm not written to manifest"
    )

    # Recovered extrinsic should be close to GT (within 15mm for translation).
    recovered = list(post_cam0["extrinsic"])
    for i in range(3):
        assert abs(recovered[i] - gt_6vec[i]) < 15.0, (
            f"translation[{i}] = {recovered[i]:.1f}mm, expected ≈ {gt_6vec[i]:.1f}mm"
        )
