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


def test_vision_find_unknown_detector():
    """Detector name not in DETECTORS registry → error=unknown_detector."""
    from unittest.mock import MagicMock as _MM

    from robot_md.mcp.tools.vision_find import vision_find_tool
    from robot_md.robot_spec import ObjectDescriptor, VisionBlock

    spec = _MM()
    spec.vision = VisionBlock(object_descriptors=(
        ObjectDescriptor(id="mystery", detector="unknown_kind", params={}),
    ))
    ctx = _MM()
    ctx.backend = _MM()
    ctx.spec = spec
    r = vision_find_tool(ctx, descriptor_id="mystery")
    assert r["status"] == "error"
    assert r["error"]["reason"] == "unknown_detector"


def test_vision_find_no_perception():
    """Backend without _perception attribute → error=no_perception."""
    from unittest.mock import MagicMock as _MM

    from robot_md.mcp.tools.vision_find import vision_find_tool
    from robot_md.robot_spec import ObjectDescriptor, VisionBlock

    spec = _MM()
    spec.vision = VisionBlock(object_descriptors=(
        ObjectDescriptor(id="x", detector="hsv", params={"h_ranges": [[0, 10]]}),
    ))
    ctx = _MM()
    ctx.backend = _MM(spec=None)  # has backend, but configure _perception absent
    # MagicMock auto-creates attributes, so explicitly remove _perception:
    ctx.backend._perception = None
    ctx.spec = spec
    r = vision_find_tool(ctx, descriptor_id="x")
    assert r["status"] == "error"
    assert r["error"]["reason"] == "no_perception"


def test_vision_find_depth_patch_is_clamped():
    """Radius formula must clamp — huge detection should not median over 200x200."""
    from unittest.mock import MagicMock as _MM

    import cv2
    import numpy as np

    from robot_md.mcp.tools.vision_find import vision_find_tool
    from robot_md.robot_spec import ObjectDescriptor, VisionBlock

    # Huge red region in a large frame.
    rgb = np.full((800, 1200, 3), 240, dtype=np.uint8)
    cv2.rectangle(rgb, (200, 200), (600, 600), (40, 40, 220), -1)  # 400x400 red blob
    # Depth: 500mm inside the blob area (we want to test the sampling radius),
    # 3000mm background (the "wrong" depth that a too-wide patch would pick up).
    depth = np.full((800, 1200), 3000, dtype=np.uint16)
    # 100x100 region: fully encloses the clamped 31x31 patch (r=15, centered at 400,400),
    # but is smaller than the unclamped 201x201 patch so the median would be dominated by 3000mm.
    depth[350:450, 350:450] = 500
    K = np.array([[500.0, 0, 600.0], [0, 500.0, 400.0], [0, 0, 1.0]])

    per = _MM()
    per.grab_frame.return_value = (rgb, depth, K)
    backend = _MM()
    backend._perception = per
    spec = _MM()
    spec.vision = VisionBlock(object_descriptors=(
        ObjectDescriptor("red_lego", "hsv",
                         {"h_ranges": [[0, 10], [170, 180]], "s_min": 80, "v_min": 80}),
    ))
    ctx = _MM()
    ctx.backend = backend
    ctx.spec = spec

    r = vision_find_tool(ctx, descriptor_id="red_lego")
    assert r["status"] == "ok"
    # With an unbounded radius (area ~160000 → r=100 → 201x201 patch spanning [300..500,300..500]),
    # the median of that window includes both 500mm and 3000mm. A clamp at r=15 keeps the
    # sample inside the 500mm sub-region and returns ~500mm.
    assert abs(r["depth_mm"] - 500) < 50, (
        f"depth_mm={r['depth_mm']} — radius clamp missing? patch may be sampling background."
    )
