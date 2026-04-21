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


async def test_discover_probe_direction_reports_shift():
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

    r = await discover_tool(
        ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}]
    )
    pd = r["results"]["probe_direction"]
    assert pd["status"] == "ok"
    assert pd["joint"] == "shoulder_pan"
    assert pd["delta"] == 30
    assert pd["px_shift"] > 10
    assert pd["direction"] == "positive_delta→image_right"
    # px_per_step rough sanity — 30px / 30 steps ≈ 1.0 (±50%)
    assert 0.5 < pd["px_per_step"] < 2.0


async def test_discover_probe_direction_no_hardware():
    """Missing backend/bus/perception → no_hardware status."""
    ctx = MagicMock()
    ctx.backend = None
    from robot_md.mcp.tools.discover import discover_tool

    r = await discover_tool(
        ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}]
    )
    assert r["results"]["probe_direction"]["status"] == "no_hardware"


async def test_discover_probe_direction_no_motion_detected():
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

    r = await discover_tool(
        ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}]
    )
    assert r["results"]["probe_direction"]["status"] == "no_motion_detected"


async def test_discover_probe_direction_returns_bus_to_start():
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

    await discover_tool(ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}])
    # Last write should be the starting positions (return-home).
    assert bus.written[-1]["shoulder_pan"] == 2048
    assert bus.written[-1]["gripper"] == 1700


async def test_discover_probe_direction_empty_read_returns_no_position_read():
    """Bus returns {} → status=no_position_read; NO write before restore."""
    import cv2
    import numpy as np

    rgb = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(rgb, (140, 50), (160, 150), (255, 255, 255), -1)

    class _EmptyReadBus:
        def __init__(self):
            self.written = []

        def torque(self, on):
            pass

        def write_positions(self, p):
            self.written.append(dict(p))

        def read_positions(self):
            return {}  # closed bus

    per = MagicMock()
    per.grab_frame.return_value = (rgb, np.full((200, 300), 500, dtype=np.uint16), None)
    backend = MagicMock()
    backend._perception = per
    bus = _EmptyReadBus()
    backend._servo_bus = bus
    ctx = MagicMock()
    ctx.spec = MagicMock()
    ctx.spec.vision = VisionBlock(object_descriptors=())
    ctx.backend = backend

    from robot_md.mcp.tools.discover import discover_tool

    r = await discover_tool(
        ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}]
    )
    assert r["results"]["probe_direction"]["status"] == "no_position_read"
    # Critical: no write should have happened.
    assert bus.written == []


async def test_discover_probe_direction_partial_read_no_joint_returns_no_position_read():
    """Bus returns partial dict without the probed joint → no_position_read."""
    import cv2
    import numpy as np

    rgb = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(rgb, (140, 50), (160, 150), (255, 255, 255), -1)

    class _PartialBus:
        def __init__(self):
            self.written = []

        def torque(self, on):
            pass

        def write_positions(self, p):
            self.written.append(dict(p))

        def read_positions(self):
            return {"gripper": 1700}  # shoulder_pan omitted

    per = MagicMock()
    per.grab_frame.return_value = (rgb, np.full((200, 300), 500, dtype=np.uint16), None)
    backend = MagicMock()
    backend._perception = per
    bus = _PartialBus()
    backend._servo_bus = bus
    ctx = MagicMock()
    ctx.spec = MagicMock()
    ctx.spec.vision = VisionBlock(object_descriptors=())
    ctx.backend = backend

    from robot_md.mcp.tools.discover import discover_tool

    r = await discover_tool(
        ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}]
    )
    assert r["results"]["probe_direction"]["status"] == "no_position_read"
    assert bus.written == []


async def test_discover_probe_direction_torque_raise_does_not_escape():
    """Any bus exception converts to a status, not a raise."""
    import cv2
    import numpy as np

    rgb = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(rgb, (140, 50), (160, 150), (255, 255, 255), -1)

    class _TorqueExplodesBus:
        def torque(self, on):
            raise RuntimeError("bus closed")

        def write_positions(self, p):
            pass

        def read_positions(self):
            return {"shoulder_pan": 2048}

    per = MagicMock()
    per.grab_frame.return_value = (rgb, np.full((200, 300), 500, dtype=np.uint16), None)
    backend = MagicMock()
    backend._perception = per
    backend._servo_bus = _TorqueExplodesBus()
    ctx = MagicMock()
    ctx.spec = MagicMock()
    ctx.spec.vision = VisionBlock(object_descriptors=())
    ctx.backend = backend

    from robot_md.mcp.tools.discover import discover_tool

    r = await discover_tool(
        ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}]
    )
    # Must not raise. Status is a failure marker.
    pd = r["results"]["probe_direction"]
    assert pd["status"] in ("bus_error", "no_frame_after")


async def test_discover_probe_direction_px_shift_is_centroid_diff_not_width_times_two():
    """A 100px-wide bar shifted 30px must report ~30, not ~65 (bar_width + shift bug)."""
    import cv2
    import numpy as np

    # 100-px wide bar shifted by 30 px.
    rgb1 = np.zeros((200, 400, 3), dtype=np.uint8)
    cv2.rectangle(rgb1, (100, 50), (200, 150), (255, 255, 255), -1)  # u centroid ≈ 150
    rgb2 = np.zeros((200, 400, 3), dtype=np.uint8)
    cv2.rectangle(rgb2, (130, 50), (230, 150), (255, 255, 255), -1)  # u centroid ≈ 180

    class _Bus:
        def __init__(self):
            self.written = []

        def torque(self, on):
            pass

        def write_positions(self, p):
            self.written.append(dict(p))

        def read_positions(self):
            return {"shoulder_pan": 2048}

    per = MagicMock()
    per.grab_frame.side_effect = [
        (rgb1, np.full((200, 400), 500, dtype=np.uint16), None),
        (rgb2, np.full((200, 400), 500, dtype=np.uint16), None),
    ]
    backend = MagicMock()
    backend._perception = per
    backend._servo_bus = _Bus()
    ctx = MagicMock()
    ctx.spec = MagicMock()
    ctx.spec.vision = VisionBlock(object_descriptors=())
    ctx.backend = backend

    from robot_md.mcp.tools.discover import discover_tool

    r = await discover_tool(
        ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}]
    )
    pd = r["results"]["probe_direction"]
    assert pd["status"] == "ok"
    # With the correct centroid-diff formula, px_shift ≈ 30. With the old
    # (max-min)//2 bug this would report ≈ 65 for a 100px bar.
    assert 20 < pd["px_shift"] < 45, f"px_shift={pd['px_shift']} — centroid-diff regression?"
    assert pd["direction"] == "positive_delta→image_right"
