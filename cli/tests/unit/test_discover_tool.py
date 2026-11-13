"""discover: declarative scene-discovery pipeline. Capture + detect steps."""

from __future__ import annotations

from unittest.mock import MagicMock

import cv2
import numpy as np

from robot_md.mcp.tools.discover import discover_tool
from robot_md.robot_spec import ObjectDescriptor, VisionBlock


def _ctx_with_two_descriptors():
    rgb = np.full((200, 300, 3), 240, dtype=np.uint8)
    cv2.rectangle(rgb, (150, 80), (200, 140), (40, 40, 220), -1)  # red @right
    cv2.rectangle(rgb, (20, 20), (60, 60), (230, 230, 230), -1)  # upper-left light
    depth = np.full((200, 300), 500, dtype=np.uint16)
    K = np.array([[500.0, 0, 150.0], [0, 500.0, 100.0], [0, 0, 1.0]])
    per = MagicMock()
    per.grab_frame.return_value = (rgb, depth, K)

    spec = MagicMock()
    spec.vision = VisionBlock(
        object_descriptors=(
            ObjectDescriptor(
                "red_lego", "hsv", {"h_ranges": [[0, 10], [170, 180]], "s_min": 80, "v_min": 80}
            ),
            ObjectDescriptor(
                "white_bowl",
                "hsv_roi",
                {"s_max": 80, "v_min": 100, "roi": {"u_max": 150, "v_max": 120}},
            ),
        )
    )
    ctx = MagicMock()
    ctx.spec = spec
    ctx.backend._perception = per
    return ctx


async def test_discover_empty_steps():
    ctx = _ctx_with_two_descriptors()
    r = await discover_tool(ctx, steps=[])
    assert r["status"] == "ok"
    assert r["results"] == {}


async def test_discover_capture_step():
    ctx = _ctx_with_two_descriptors()
    r = await discover_tool(ctx, steps=[{"capture": {}}])
    assert r["status"] == "ok"
    assert r["results"]["capture"]["status"] == "ok"
    # Shape available in the result (h, w, 3).
    assert r["results"]["capture"]["shape"] == [200, 300, 3]


async def test_discover_capture_no_backend():
    ctx = MagicMock()
    ctx.backend = None
    r = await discover_tool(ctx, steps=[{"capture": {}}])
    assert r["status"] == "ok"
    assert r["results"]["capture"]["status"] == "no_frame"


async def test_discover_detect_finds_both():
    ctx = _ctx_with_two_descriptors()
    r = await discover_tool(
        ctx,
        steps=[
            {"capture": {}},
            {"detect": {"descriptors": ["red_lego", "white_bowl"]}},
        ],
    )
    assert r["status"] == "ok"
    det = r["results"]["detect"]
    assert det["red_lego"]["status"] == "ok"
    assert det["red_lego"]["pixel"][0] > 150  # right side
    assert det["white_bowl"]["status"] == "ok"
    assert det["white_bowl"]["pixel"][0] < 150  # left side


async def test_discover_detect_without_capture_auto_captures():
    """If detect is called without prior capture, it auto-captures."""
    ctx = _ctx_with_two_descriptors()
    r = await discover_tool(ctx, steps=[{"detect": {"descriptors": ["red_lego"]}}])
    assert r["results"]["detect"]["red_lego"]["status"] == "ok"


async def test_discover_unknown_descriptor_reported_not_raised():
    ctx = _ctx_with_two_descriptors()
    r = await discover_tool(ctx, steps=[{"detect": {"descriptors": ["nonsense"]}}])
    assert r["status"] == "ok"  # discovery never raises on per-item failure
    assert r["results"]["detect"]["nonsense"]["status"] == "unknown_descriptor"


async def test_discover_unknown_step_kind_reported():
    ctx = _ctx_with_two_descriptors()
    r = await discover_tool(ctx, steps=[{"teleport": {"to": "mars"}}])
    assert r["status"] == "ok"
    assert r["results"]["teleport"]["status"] == "unknown_step"


async def test_discover_malformed_step_skipped():
    """A step with zero keys or multiple keys is silently skipped."""
    ctx = _ctx_with_two_descriptors()
    r = await discover_tool(ctx, steps=[{}, {"a": {}, "b": {}}])
    assert r["status"] == "ok"
    assert r["results"] == {}


async def test_discover_probe_direction_refuses_and_writes_nothing():
    """probe_direction moved a joint by writing the servo bus from the MCP
    process. robot-md's MCP server no longer writes the bus, so the step
    refuses, even with a bus and a camera at hand."""

    class _Bus:
        def __init__(self):
            self.calls = []

        def read_positions(self):
            self.calls.append("read_positions")
            return {"shoulder_pan": 2048}

        def write_positions(self, p):
            self.calls.append(("write_positions", dict(p)))

        def torque(self, on):
            self.calls.append(("torque", on))

    ctx = _ctx_with_two_descriptors()
    bus = _Bus()
    ctx.backend._servo_bus = bus
    r = await discover_tool(
        ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}]
    )
    pd = r["results"]["probe_direction"]
    assert pd["status"] == "refused"
    assert pd["joint"] == "shoulder_pan"
    assert "robot-md-gateway" in pd["message"]
    assert bus.calls == []


async def test_discover_probe_direction_refuses_with_no_hardware():
    ctx = MagicMock()
    ctx.backend = None
    r = await discover_tool(
        ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}]
    )
    assert r["results"]["probe_direction"]["status"] == "refused"


async def test_discover_capture_still_works_alongside_a_refused_probe():
    ctx = _ctx_with_two_descriptors()
    r = await discover_tool(
        ctx,
        steps=[{"capture": {}}, {"probe_direction": {"joint": "wrist_flex"}}],
    )
    assert r["results"]["capture"]["status"] == "ok"
    assert r["results"]["probe_direction"]["status"] == "refused"
