"""HARDWARE: teach ready → execute arm.home → verify servos reach taught pose.

Opt-in: runs only with `--run-hardware`. Requires the SO-ARM101 + OAK-D setup
with the Feetech servo bus on /dev/ttyACM0 (or the default autodetect finds it).

Operator pre-conditions BEFORE running this test:
  - Arm is powered and USB-connected.
  - The arm is physically posed in your intended 'ready' configuration
    (gripper over workspace, reachable to tabletop).
The test will record that pose, then command a move to (2048,...) and back.
"""
from __future__ import annotations

import time

import pytest


@pytest.mark.hardware
def test_pose_teach_then_home_matches(tmp_path):
    from robot_md.init import non_interactive
    from robot_md.mcp.context import load_context
    from robot_md.mcp.tools.execute_capability import execute_capability_tool
    from robot_md.poses import teach_pose

    manifest = tmp_path / "ROBOT.md"
    rc = non_interactive(
        manifest, robot_name="bob-hardware", preset_name="so-arm101", force=True,
    )
    assert rc == 0
    ctx = load_context(manifest)
    bus = ctx.backend._servo_bus

    # 1. Operator has already posed the arm. Record it.
    taught = teach_pose(bus, manifest, name="ready")
    assert "shoulder_pan" in taught, f"teach_pose returned no shoulder_pan: {taught}"

    # 2. Move every joint to a known-different position so arm.home has work to do.
    away = {k: 2048 for k in taught}
    bus.torque(True)
    try:
        bus.write_positions(away)
    finally:
        # Let the arm settle.
        time.sleep(1.5)

    # 3. Reload context so the freshly-written poses.ready is picked up by the backend.
    ctx2 = load_context(manifest)

    # 4. Execute arm.home (dry_run=False — this actually moves the arm).
    r = execute_capability_tool(
        ctx2, capability="arm.home", args={}, dry_run=False, confirm_token=None,
    )
    assert r["status"] == "ok", f"execute_capability arm.home failed: {r}"

    # 5. Give motion time to complete, then verify servos reached the taught pose.
    time.sleep(2.0)
    final = bus.read_positions()
    for joint, target in taught.items():
        delta = abs(final.get(joint, -99999) - target)
        assert delta < 30, (
            f"joint {joint}: target={target} final={final.get(joint)} delta={delta}"
        )
