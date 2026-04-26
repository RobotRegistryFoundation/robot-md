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
    spec.vision = VisionBlock(
        object_descriptors=(
            ObjectDescriptor(
                id="red_lego",
                detector="hsv",
                params={"h_ranges": [[0, 10], [170, 180]], "s_min": 80, "v_min": 80},
            ),
        )
    )

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
    spec.vision = VisionBlock(
        object_descriptors=(ObjectDescriptor(id="mystery", detector="unknown_kind", params={}),)
    )
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
    spec.vision = VisionBlock(
        object_descriptors=(
            ObjectDescriptor(id="x", detector="hsv", params={"h_ranges": [[0, 10]]}),
        )
    )
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
    spec.vision = VisionBlock(
        object_descriptors=(
            ObjectDescriptor(
                "red_lego", "hsv", {"h_ranges": [[0, 10], [170, 180]], "s_min": 80, "v_min": 80}
            ),
        )
    )
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


def test_vision_find_filters_oak_d_no_data_sentinel():
    """OAK-D's stereo depth fills textureless surfaces (lego, bowl) with the
    65535mm 'no data' sentinel. Without filtering, the patch median around
    the centroid is dominated by saturated values and depth lands at ~15m
    even when valid neighboring pixels are at 40cm."""
    rgb = np.zeros((200, 300, 3), dtype=np.uint8)
    rgb[:] = (240, 240, 240)
    cv2.rectangle(rgb, (120, 60), (180, 120), (40, 40, 220), -1)
    # Depth: most of the patch around the red blob is saturated (65535).
    # A few scattered valid pixels (within the patch) at 400mm — the
    # legitimate depth of the textureless lego surface gleaned from edges.
    depth = np.full((200, 300), 65535, dtype=np.uint16)
    depth[80:85, 145:155] = 400  # small valid patch inside the blob
    K = np.array([[500.0, 0, 150.0], [0, 500.0, 100.0], [0, 0, 1.0]])

    per = MagicMock()
    per.grab_frame.return_value = (rgb, depth, K)
    backend = MagicMock()
    backend._perception = per

    spec = MagicMock()
    spec.vision = VisionBlock(
        object_descriptors=(
            ObjectDescriptor(
                id="red_lego",
                detector="hsv",
                params={"h_ranges": [[0, 10], [170, 180]], "s_min": 80, "v_min": 80},
            ),
        )
    )
    ctx = MagicMock()
    ctx.backend = backend
    ctx.spec = spec

    r = vision_find_tool(ctx, descriptor_id="red_lego")
    assert r["status"] == "ok"
    # If the saturation filter is broken, depth_mm would be ~65535 (or its
    # median with a few 400s mixed in: still >>10000). With the filter,
    # depth_mm should be near 400.
    assert r["depth_mm"] < 1000, (
        f"depth filter broken — saturation values pulled median to {r['depth_mm']}mm"
    )
    assert 350 < r["depth_mm"] < 500


def test_vision_find_passes_depth_frame_to_detector():
    """vision_find_tool must pass `depth_frame` to the detector so descriptor
    `min_depth_mm`/`max_depth_mm`/`strict_depth` actually take effect.
    Bug: PR #10 added depth bounds to the init scaffold but vision_find
    only passed the RGB frame, so depth filtering was silently skipped."""
    rgb = np.zeros((200, 300, 3), dtype=np.uint8)
    rgb[:] = (240, 240, 240)
    cv2.rectangle(rgb, (50, 50), (100, 100), (40, 40, 220), -1)  # red blob in upper-left
    cv2.rectangle(rgb, (200, 130), (260, 170), (40, 40, 220), -1)  # red blob in lower-right
    # Depth: upper-left blob at 6m (background, out of range);
    # lower-right blob at 400mm (in range).
    depth = np.full((200, 300), 65535, dtype=np.uint16)
    depth[40:110, 40:110] = 6000
    depth[120:180, 195:265] = 400
    K = np.array([[500.0, 0, 150.0], [0, 500.0, 100.0], [0, 0, 1.0]])

    per = MagicMock()
    per.grab_frame.return_value = (rgb, depth, K)
    backend = MagicMock()
    backend._perception = per
    spec = MagicMock()
    # Strict depth filter — must reject the 6m background blob and pick
    # the 400mm in-range blob.
    spec.vision = VisionBlock(
        object_descriptors=(
            ObjectDescriptor(
                id="red_lego",
                detector="hsv",
                params={
                    "h_ranges": [[0, 10], [170, 180]],
                    "s_min": 80,
                    "v_min": 80,
                    "min_depth_mm": 100,
                    "max_depth_mm": 800,
                    "strict_depth": True,
                },
            ),
        )
    )
    ctx = MagicMock()
    ctx.backend = backend
    ctx.spec = spec

    r = vision_find_tool(ctx, descriptor_id="red_lego")
    assert r["status"] == "ok"
    # Centroid should land on the 400mm blob (lower-right, around (230, 150))
    u, v = r["pixel"]
    assert 195 < u < 265 and 120 < v < 180, (
        f"detector matched wrong blob: pixel ({u},{v}) — depth filter not applied"
    )
    assert r["depth_mm"] < 800


def test_vision_find_patch_median_honors_descriptor_depth_bounds():
    """When the descriptor declares min/max depth, the patch median around
    the centroid should be filtered by THOSE bounds, not just the saturation
    filter. Otherwise a centroid that lands on a stereo-hole pixel can have
    its depth read from surrounding background pixels (e.g. a back wall at
    600mm when bob's workspace is 100-500mm)."""
    rgb = np.zeros((200, 300, 3), dtype=np.uint8)
    rgb[:] = (240, 240, 240)
    cv2.rectangle(rgb, (135, 85), (165, 115), (40, 40, 220), -1)  # red blob (~900px)
    # The lego region is full of stereo holes (depth==0) — typical of
    # matte plastic. The detector's permissive mask (unknown | in_range)
    # still passes the holes so it lands on the lego centroid. The patch
    # around the centroid then samples surrounding background (600mm
    # wall, OUT of band) — the bug we're testing for.
    depth = np.full((200, 300), 600, dtype=np.uint16)
    depth[85:115, 135:165] = 0  # stereo holes covering the lego region
    K = np.array([[500.0, 0, 150.0], [0, 500.0, 100.0], [0, 0, 1.0]])

    per = MagicMock()
    per.grab_frame.return_value = (rgb, depth, K)
    backend = MagicMock()
    backend._perception = per
    spec = MagicMock()
    spec.vision = VisionBlock(
        object_descriptors=(
            ObjectDescriptor(
                id="red_lego",
                detector="hsv",
                params={
                    "h_ranges": [[0, 10], [170, 180]],
                    "s_min": 80,
                    "v_min": 80,
                    "min_depth_mm": 100,
                    "max_depth_mm": 500,
                },
            ),
        )
    )
    ctx = MagicMock()
    ctx.backend = backend
    ctx.spec = spec

    r = vision_find_tool(ctx, descriptor_id="red_lego")
    # No valid in-band pixels in the patch → depth_mm should be nan, NOT
    # the 600mm out-of-band median. xyz collapses to nan accordingly.
    assert r["status"] == "ok"
    import math

    assert math.isnan(r["depth_mm"]), (
        f"expected nan when no in-band depth pixels; got {r['depth_mm']}"
    )
