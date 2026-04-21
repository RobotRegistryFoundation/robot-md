"""End-to-end hardware proof: init → calibrate extrinsic → pick a red LEGO.
Operator places a red LEGO brick on the workspace before running.

This test will MOVE the arm. The operator must be physically present
and ready to e-stop if the motion looks wrong.
"""

from __future__ import annotations

import pytest


@pytest.mark.hardware
def test_real_arm_pick_red_lego_after_calibrate(tmp_path, monkeypatch):
    from robot_md.backends.feetech_depthai.perception import Perception
    from robot_md.backends.feetech_depthai.servo import ServoBus
    from robot_md.init import default_flow
    from robot_md.init_phases import phase_calibrate_extrinsic
    from robot_md.mcp.context import load_context
    from robot_md.mcp.tools.execute_capability import execute_capability_tool
    from robot_md.parser import parse_file
    from robot_md.robot_spec import RobotSpec

    manifest = tmp_path / "ROBOT.md"
    default_flow(
        manifest,
        robot_name="hwpick",
        preset_name="so-arm101",
        do_register=False,
        do_install_mcp=False,
        do_install_skill=False,
        do_refresh_claude_md=False,
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

    spec = RobotSpec.from_parsed(parse_file(manifest))
    bus = ServoBus.from_spec(spec)
    cam = Perception.from_spec(spec)
    bus.open()
    cam.open()
    try:
        # 1. Calibrate extrinsic.
        cal = phase_calibrate_extrinsic(
            manifest,
            bus=bus,
            camera=cam,
            interactive=True,
            n_poses=6,
        )
        assert cal.status == "ok", f"calibration failed: {cal.message}"

        # 2. Re-parse (now has calibrated extrinsic) and dispatch arm.pick.
        # Use load_context so the full MCP plumbing (safety gates, estop,
        # capability declaration checks) is exercised — same path as production.
        ctx = load_context(manifest)
        result = execute_capability_tool(
            ctx,
            capability="arm.pick",
            args={"target": "red_lego"},
            dry_run=False,
            confirm_token=None,
        )
        assert result.get("status") == "ok", f"pick failed: {result}"
    finally:
        cam.close()
        bus.close()
