"""Integration: discover → vision.find → execute_capability(arm.home) chain, all dry.

Uses a faked perception + servo bus. Validates the plumbing (manifest → context
→ MCP tools), not the hardware. Gated with @pytest.mark.integration.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest


@pytest.mark.integration
def test_discover_then_vision_find_then_execute(tmp_path):
    from robot_md.backends.base import ExecutionResult
    from robot_md.init import non_interactive
    from robot_md.mcp.context import load_context
    from robot_md.mcp.tools.discover import discover_tool
    from robot_md.mcp.tools.execute_capability import execute_capability_tool
    from robot_md.mcp.tools.vision_find import vision_find_tool
    from robot_md.poses import write_pose_to_manifest

    # 1. Fresh so-arm101 manifest (ships red_lego + white_bowl from Task 21).
    manifest = tmp_path / "ROBOT.md"
    rc = non_interactive(manifest, robot_name="bob", preset_name="so-arm101", force=True)
    assert rc == 0

    # 2. Teach a stub 'ready' pose so arm.home resolves to it.
    write_pose_to_manifest(
        manifest,
        name="ready",
        joints={"shoulder_pan": 1950, "shoulder_lift": 1700, "elbow_flex": 2400,
                "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700},
    )

    # 3. Load context + swap in fake backend hardware.
    ctx = load_context(manifest)
    rgb = np.full((720, 1280, 3), 240, dtype=np.uint8)
    cv2.rectangle(rgb, (500, 380), (600, 440), (40, 40, 220), -1)   # red lego right-center
    cv2.rectangle(rgb, (50, 100), (400, 350), (230, 230, 230), -1)  # bowl upper-left
    depth = np.full((720, 1280), 500, dtype=np.uint16)
    K = np.array([[979.0, 0, 666.0], [0, 979.0, 348.0], [0, 0, 1.0]])
    per = MagicMock()
    per.grab_frame.return_value = (rgb, depth, K)
    bus = MagicMock()
    bus.read_positions.return_value = {"shoulder_pan": 2048, "gripper": 1700}
    backend = MagicMock()
    backend._perception = per
    backend._servo_bus = bus
    backend.capabilities.return_value = frozenset(
        {"arm.home", "arm.pick", "arm.place", "status.report"}
    )
    backend.read_only_capabilities = frozenset({"status.report"})
    backend.execute.return_value = ExecutionResult(
        status="ok",
        trajectory=[{"t": 0.0, "joints": {"shoulder_pan": 1950}}],
        events=[],
        error=None,
    )
    ctx.backend = backend

    # --- Step A: discover — capture + detect ---
    disc = discover_tool(ctx, steps=[
        {"capture": {}},
        {"detect": {"descriptors": ["red_lego", "white_bowl"]}},
    ])
    assert disc["status"] == "ok"
    det = disc["results"]["detect"]
    assert det["red_lego"]["status"] == "ok"
    assert det["white_bowl"]["status"] == "ok"

    # --- Step B: vision.find — resolve one descriptor to camera XYZ ---
    vf = vision_find_tool(ctx, descriptor_id="red_lego")
    assert vf["status"] == "ok"
    assert vf["descriptor"] == "red_lego"
    assert vf["depth_mm"] == 500
    assert len(vf["camera_xyz_mm"]) == 3

    # --- Step C: execute_capability(arm.home) — dry-run ---
    exe = execute_capability_tool(
        ctx, capability="arm.home", args={}, dry_run=True, confirm_token=None
    )
    assert exe["status"] == "ok", f"execute_capability blocked: {exe}"
