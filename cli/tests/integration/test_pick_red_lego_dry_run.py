"""Integration: discover → vision.find → execute_capability(arm.home) chain, all dry.

Uses a faked perception + servo bus. Validates the plumbing (manifest → context
→ MCP tools), not the hardware. Gated with @pytest.mark.integration.

Also hosts the v0.6.1 end-to-end pick-red-lego test (no hardware) that
exercises init + auto-calibrate + arm.pick descriptor → IK → trajectory.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
import yaml


@pytest.mark.integration
async def test_discover_then_vision_find_then_execute(tmp_path):
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
    disc = await discover_tool(ctx, steps=[
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


# --------------------------------------------------------------------------- #
# v0.6.1: end-to-end pipeline test                                            #
# --------------------------------------------------------------------------- #


def test_v061_pipeline_end_to_end(tmp_path: Path):
    """End-to-end: robot-md init + arm.pick("red_lego") dry-run succeeds.

    No hardware. Uses mocked servo bus + perception to confirm the full
    v0.6.1 pipeline: auto-calibrated ready pose → extrinsic → IK →
    trajectory → dispatch.
    """
    from robot_md.init import default_flow
    from robot_md.backends.feetech_depthai.capabilities import _arm_pick
    from robot_md.init_phases import PhaseResult

    @dataclass
    class B:
        raw_frontmatter: dict
        _servo_bus: Any
        _motion: Any
        _perception: Any
        _spec: Any = None

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
            out, robot_name="lego-bot", preset_name="so-arm101",
            do_install_mcp=False, do_install_skill=False,
            do_register=False, do_refresh_claude_md=False,
        )
    assert rc == 0, f"init failed rc={rc}"

    # Manifest exists and has poses.ready populated (auto-calibrate ran).
    fm_text = out.read_text()
    fm = yaml.safe_load(fm_text.split("---")[1])
    ready = ((fm["physics"].get("poses") or {}).get("ready") or {}).get("joints")
    assert ready is not None and len(ready) >= 6, f"ready pose not auto-calibrated: {ready}"

    # Now simulate arm.pick("red_lego") against this manifest.
    bus = MagicMock()
    bus.read_positions.return_value = ready
    bus.torque = MagicMock()
    perception = MagicMock()
    # Camera-frame XYZ chosen to land inside the preset-default workspace
    # after the so-arm101 default extrinsic (OAK-D at (400, 0, 300) looking
    # at (200, 0, 0)) maps it into base frame. (0, 0, 340) → ~(211, 0, 17).
    perception.vision_find.return_value = {
        "status": "ok", "descriptor": "red_lego", "xyz_cam_mm": (0.0, 0.0, 340.0),
    }
    backend = B(raw_frontmatter=fm, _servo_bus=bus, _motion=MagicMock(), _perception=perception)

    result = _arm_pick(backend, args={"target": "red_lego"}, dry_run=True, estop=None)
    assert result.status == "ok", result.error
    assert result.trajectory is not None
    phases = [wp["phase"] for wp in result.trajectory]
    assert "approach" in phases and "grasp_close" in phases and "lift" in phases
