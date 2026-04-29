from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.realsense import RealsenseBackend


def test_aligned_depth_uses_align_processor() -> None:
    aligned_depth = MagicMock()
    aligned_depth.get_data.return_value = b"ALIGNED_DEPTH"
    align_processor = MagicMock()
    align_processor.process.return_value.get_depth_frame.return_value = aligned_depth
    frames = MagicMock()
    pipeline = MagicMock()
    pipeline.wait_for_frames.return_value = frames

    b = RealsenseBackend()
    b._pipeline = pipeline
    b._align_processor = align_processor
    result = b.execute("realsense.aligned_depth", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    payload = result.events[-1].data
    assert payload["frame_bytes"] == b"ALIGNED_DEPTH"
    assert payload["aligned_to"] == "color"
    align_processor.process.assert_called_once_with(frames)
