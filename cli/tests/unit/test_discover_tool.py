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
    cv2.rectangle(rgb, (20, 20), (60, 60), (230, 230, 230), -1)   # upper-left light
    depth = np.full((200, 300), 500, dtype=np.uint16)
    K = np.array([[500.0, 0, 150.0], [0, 500.0, 100.0], [0, 0, 1.0]])
    per = MagicMock()
    per.grab_frame.return_value = (rgb, depth, K)

    spec = MagicMock()
    spec.vision = VisionBlock(object_descriptors=(
        ObjectDescriptor("red_lego", "hsv",
                         {"h_ranges": [[0, 10], [170, 180]], "s_min": 80, "v_min": 80}),
        ObjectDescriptor("white_bowl", "hsv_roi",
                         {"s_max": 80, "v_min": 100, "roi": {"u_max": 150, "v_max": 120}}),
    ))
    ctx = MagicMock()
    ctx.spec = spec
    ctx.backend._perception = per
    return ctx


def test_discover_empty_steps():
    ctx = _ctx_with_two_descriptors()
    r = discover_tool(ctx, steps=[])
    assert r["status"] == "ok"
    assert r["results"] == {}


def test_discover_capture_step():
    ctx = _ctx_with_two_descriptors()
    r = discover_tool(ctx, steps=[{"capture": {}}])
    assert r["status"] == "ok"
    assert r["results"]["capture"]["status"] == "ok"
    # Shape available in the result (h, w, 3).
    assert r["results"]["capture"]["shape"] == [200, 300, 3]


def test_discover_capture_no_backend():
    ctx = MagicMock()
    ctx.backend = None
    r = discover_tool(ctx, steps=[{"capture": {}}])
    assert r["status"] == "ok"
    assert r["results"]["capture"]["status"] == "no_frame"


def test_discover_detect_finds_both():
    ctx = _ctx_with_two_descriptors()
    r = discover_tool(ctx, steps=[
        {"capture": {}},
        {"detect": {"descriptors": ["red_lego", "white_bowl"]}},
    ])
    assert r["status"] == "ok"
    det = r["results"]["detect"]
    assert det["red_lego"]["status"] == "ok"
    assert det["red_lego"]["pixel"][0] > 150  # right side
    assert det["white_bowl"]["status"] == "ok"
    assert det["white_bowl"]["pixel"][0] < 150  # left side


def test_discover_detect_without_capture_auto_captures():
    """If detect is called without prior capture, it auto-captures."""
    ctx = _ctx_with_two_descriptors()
    r = discover_tool(ctx, steps=[{"detect": {"descriptors": ["red_lego"]}}])
    assert r["results"]["detect"]["red_lego"]["status"] == "ok"


def test_discover_unknown_descriptor_reported_not_raised():
    ctx = _ctx_with_two_descriptors()
    r = discover_tool(ctx, steps=[{"detect": {"descriptors": ["nonsense"]}}])
    assert r["status"] == "ok"  # discovery never raises on per-item failure
    assert r["results"]["detect"]["nonsense"]["status"] == "unknown_descriptor"


def test_discover_unknown_step_kind_reported():
    ctx = _ctx_with_two_descriptors()
    r = discover_tool(ctx, steps=[{"teleport": {"to": "mars"}}])
    assert r["status"] == "ok"
    assert r["results"]["teleport"]["status"] == "unknown_step"


def test_discover_malformed_step_skipped():
    """A step with zero keys or multiple keys is silently skipped."""
    ctx = _ctx_with_two_descriptors()
    r = discover_tool(ctx, steps=[{}, {"a": {}, "b": {}}])
    assert r["status"] == "ok"
    assert r["results"] == {}
