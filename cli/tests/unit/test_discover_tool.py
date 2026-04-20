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


def test_discover_probe_direction_reports_shift():
    """Move 30 steps; white bar shifts from u=150 to u=180 (right) → positive direction."""
    import cv2
    import numpy as np

    rgb1 = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(rgb1, (140, 50), (160, 150), (255, 255, 255), -1)  # at u≈150
    frame1 = (rgb1, np.full((200, 300), 500, dtype=np.uint16), None)

    rgb2 = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(rgb2, (170, 50), (190, 150), (255, 255, 255), -1)  # at u≈180 (+30 px)
    frame2 = (rgb2, np.full((200, 300), 500, dtype=np.uint16), None)

    class _PosBus:
        def __init__(self):
            self.written = []
        def torque(self, on):
            pass
        def write_positions(self, p):
            self.written.append(dict(p))
        def read_positions(self):
            return {"shoulder_pan": 2048}

    per = MagicMock()
    per.grab_frame.side_effect = [frame1, frame2]
    backend = MagicMock()
    backend._perception = per
    backend._servo_bus = _PosBus()
    ctx = MagicMock()
    ctx.spec = MagicMock()
    ctx.spec.vision = VisionBlock(object_descriptors=())
    ctx.backend = backend

    from robot_md.mcp.tools.discover import discover_tool
    r = discover_tool(ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}])
    pd = r["results"]["probe_direction"]
    assert pd["status"] == "ok"
    assert pd["joint"] == "shoulder_pan"
    assert pd["delta"] == 30
    assert pd["px_shift"] > 10
    assert pd["direction"] == "positive_delta→image_right"
    # px_per_step rough sanity — 30px / 30 steps ≈ 1.0 (±50%)
    assert 0.5 < pd["px_per_step"] < 2.0


def test_discover_probe_direction_no_hardware():
    """Missing backend/bus/perception → no_hardware status."""
    ctx = MagicMock()
    ctx.backend = None
    from robot_md.mcp.tools.discover import discover_tool
    r = discover_tool(ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}])
    assert r["results"]["probe_direction"]["status"] == "no_hardware"


def test_discover_probe_direction_no_motion_detected():
    """Identical before/after frames → no_motion_detected (not a crash)."""
    import cv2
    import numpy as np

    rgb = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(rgb, (140, 50), (160, 150), (255, 255, 255), -1)
    # Both calls return the SAME frame (numpy copy to avoid identity gotchas).
    frames = [(rgb.copy(), np.full((200, 300), 500, dtype=np.uint16), None) for _ in range(2)]

    class _NoopBus:
        def torque(self, on):
            pass
        def write_positions(self, p):
            pass
        def read_positions(self):
            return {"shoulder_pan": 2048}

    per = MagicMock()
    per.grab_frame.side_effect = frames
    backend = MagicMock()
    backend._perception = per
    backend._servo_bus = _NoopBus()
    ctx = MagicMock()
    ctx.spec = MagicMock()
    ctx.spec.vision = VisionBlock(object_descriptors=())
    ctx.backend = backend

    from robot_md.mcp.tools.discover import discover_tool
    r = discover_tool(ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}])
    assert r["results"]["probe_direction"]["status"] == "no_motion_detected"


def test_discover_probe_direction_returns_bus_to_start():
    """After probe, the bus must be commanded back to the original position."""
    import cv2
    import numpy as np

    rgb1 = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(rgb1, (140, 50), (160, 150), (255, 255, 255), -1)
    rgb2 = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(rgb2, (170, 50), (190, 150), (255, 255, 255), -1)

    class _Bus:
        def __init__(self):
            self.written = []
        def torque(self, on):
            pass
        def write_positions(self, p):
            self.written.append(dict(p))
        def read_positions(self):
            return {"shoulder_pan": 2048, "gripper": 1700}

    bus = _Bus()
    per = MagicMock()
    per.grab_frame.side_effect = [
        (rgb1, np.full((200, 300), 500, dtype=np.uint16), None),
        (rgb2, np.full((200, 300), 500, dtype=np.uint16), None),
    ]
    backend = MagicMock()
    backend._perception = per
    backend._servo_bus = bus
    ctx = MagicMock()
    ctx.spec = MagicMock()
    ctx.spec.vision = VisionBlock(object_descriptors=())
    ctx.backend = backend

    from robot_md.mcp.tools.discover import discover_tool
    discover_tool(ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}])
    # Last write should be the starting positions (return-home).
    assert bus.written[-1]["shoulder_pan"] == 2048
    assert bus.written[-1]["gripper"] == 1700
