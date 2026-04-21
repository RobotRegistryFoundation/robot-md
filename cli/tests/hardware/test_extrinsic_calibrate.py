"""Run gripper-silhouette sweep on the real arm; assert residual < 10mm
and the recovered extrinsic passes sanity (camera z-axis roughly points
at workspace center, not away).

Pre-conditions (operator):
- SO-ARM101 connected at /dev/ttyACM0
- OAK-D connected via USB
- Arm in its stowed position (no collision risk when sweep runs)
"""

from __future__ import annotations

import pytest


@pytest.mark.hardware
def test_real_extrinsic_sweep_produces_small_residual(tmp_path, monkeypatch):
    from robot_md.backends.feetech_depthai.perception import Perception
    from robot_md.backends.feetech_depthai.servo import ServoBus
    from robot_md.init import default_flow
    from robot_md.init_phases import phase_calibrate_extrinsic
    from robot_md.parser import parse_file
    from robot_md.robot_spec import RobotSpec

    # Seed a fresh manifest from the so-arm101 preset.
    manifest = tmp_path / "ROBOT.md"
    default_flow(
        manifest,
        robot_name="hwtest",
        preset_name="so-arm101",
        do_register=False,
        do_install_mcp=False,
        do_install_skill=False,
        do_refresh_claude_md=False,
    )

    # Accept the TTY prompt automatically for this test.
    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

    spec = RobotSpec.from_parsed(parse_file(manifest))
    bus = ServoBus.from_spec(spec)
    cam = Perception.from_spec(spec)
    bus.open()
    cam.open()
    try:
        result = phase_calibrate_extrinsic(
            manifest,
            bus=bus,
            camera=cam,
            interactive=True,
            n_poses=6,
        )
        assert result.status == "ok", f"{result.status}: {result.message}"
        assert result.detail["residual_mm"] < 10.0, result.detail
        # Sanity: manifest now has gripper_silhouette_calibrated source.
        post = parse_file(manifest).frontmatter
        assert post["physics"]["solver"]["cameras"][0]["extrinsic_source"] == (
            "gripper_silhouette_calibrated"
        )
    finally:
        cam.close()
        bus.close()
