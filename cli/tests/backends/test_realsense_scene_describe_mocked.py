from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.realsense import RealsenseBackend


def test_scene_describe_returns_snapshot_with_color_bytes() -> None:
    color_frame = MagicMock()
    color_frame.get_data.return_value = b"COLOR_BYTES"
    frames = MagicMock()
    frames.get_color_frame.return_value = color_frame
    pipeline = MagicMock()
    pipeline.wait_for_frames.return_value = frames

    b = RealsenseBackend()
    b._pipeline = pipeline
    snap = b.scene_describe()
    assert snap.frame == b"COLOR_BYTES"
    assert snap.detections == ()
    assert snap.joint_state == {}


def test_scene_describe_with_no_pipeline_returns_empty() -> None:
    b = RealsenseBackend()
    snap = b.scene_describe()
    assert snap.frame is None
