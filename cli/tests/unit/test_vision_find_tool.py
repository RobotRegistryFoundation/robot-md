"""vision.find resolves an object_descriptor id to a 3-D camera-frame point."""
from __future__ import annotations

from unittest.mock import MagicMock

import cv2
import numpy as np

from robot_md.mcp.tools.vision_find import vision_find_tool
from robot_md.robot_spec import ObjectDescriptor, VisionBlock


def _ctx_with_descriptor_and_frame():
    rgb = np.zeros((200, 300, 3), dtype=np.uint8)
    rgb[:] = (240, 240, 240)
    cv2.rectangle(rgb, (120, 60), (180, 120), (40, 40, 220), -1)  # red blob ~center
    depth = np.full((200, 300), 500, dtype=np.uint16)  # 500mm uniformly
    K = np.array([[500.0, 0, 150.0], [0, 500.0, 100.0], [0, 0, 1.0]])

    per = MagicMock()
    per.grab_frame.return_value = (rgb, depth, K)

    backend = MagicMock()
    backend._perception = per

    spec = MagicMock()
    spec.vision = VisionBlock(object_descriptors=(
        ObjectDescriptor(
            id="red_lego",
            detector="hsv",
            params={"h_ranges": [[0, 10], [170, 180]], "s_min": 80, "v_min": 80},
        ),
    ))

    ctx = MagicMock()
    ctx.backend = backend
    ctx.spec = spec
    return ctx


def test_vision_find_returns_3d_point():
    ctx = _ctx_with_descriptor_and_frame()
    r = vision_find_tool(ctx, descriptor_id="red_lego")
    assert r["status"] == "ok"
    assert r["descriptor"] == "red_lego"
    u, _v = r["pixel"]
    assert 120 < u < 180
    assert r["camera_xyz_mm"][2] == 500
    # Blob centered near image cx=150 → x_cam near zero.
    assert abs(r["camera_xyz_mm"][0]) < 50


def test_vision_find_unknown_descriptor():
    ctx = _ctx_with_descriptor_and_frame()
    r = vision_find_tool(ctx, descriptor_id="blue_widget")
    assert r["status"] == "error"
    assert r["error"]["reason"] == "unknown_descriptor"


def test_vision_find_no_detection():
    ctx = _ctx_with_descriptor_and_frame()
    ctx.backend._perception.grab_frame.return_value = (
        np.full((200, 300, 3), 240, dtype=np.uint8),
        np.full((200, 300), 500, dtype=np.uint16),
        np.array([[500.0, 0, 150.0], [0, 500.0, 100.0], [0, 0, 1.0]]),
    )
    r = vision_find_tool(ctx, descriptor_id="red_lego")
    assert r["status"] == "not_found"


def test_vision_find_no_backend():
    ctx = MagicMock()
    ctx.backend = None
    r = vision_find_tool(ctx, descriptor_id="red_lego")
    assert r["status"] == "error"
    assert r["error"]["reason"] == "no_backend"


def test_vision_find_no_frame():
    ctx = _ctx_with_descriptor_and_frame()
    ctx.backend._perception.grab_frame.return_value = None
    r = vision_find_tool(ctx, descriptor_id="red_lego")
    assert r["status"] == "error"
    assert r["error"]["reason"] == "no_frame"
