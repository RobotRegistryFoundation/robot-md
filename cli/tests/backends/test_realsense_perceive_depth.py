from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.realsense import RealsenseBackend


def test_perceive_depth_returns_z16_bytes() -> None:
    depth_frame = MagicMock()
    depth_frame.get_data.return_value = b"FAKE_DEPTH_BYTES"
    frames = MagicMock()
    frames.get_depth_frame.return_value = depth_frame
    pipeline = MagicMock()
    pipeline.wait_for_frames.return_value = frames

    b = RealsenseBackend()
    b._pipeline = pipeline
    result = b.execute("perceive.depth", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    payload = result.events[-1].data
    assert payload["frame_bytes"] == b"FAKE_DEPTH_BYTES"
    assert payload["format"] == "z16"
