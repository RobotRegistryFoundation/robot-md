from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.realsense import RealsenseBackend


def test_perceive_rgb_returns_frame_bytes() -> None:
    color_frame = MagicMock()
    color_frame.get_data.return_value = b"FAKE_RGB_BYTES"
    frames = MagicMock()
    frames.get_color_frame.return_value = color_frame
    pipeline = MagicMock()
    pipeline.wait_for_frames.return_value = frames

    b = RealsenseBackend()
    b._pipeline = pipeline
    result = b.execute("perceive.rgb", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    payload = result.events[-1].data
    assert payload["frame_bytes"] == b"FAKE_RGB_BYTES"
    assert payload["format"] == "bgr8"


def test_perceive_rgb_dry_run_short_circuits() -> None:
    b = RealsenseBackend()
    b._pipeline = MagicMock()  # would raise if called
    result = b.execute("perceive.rgb", {}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert result.events[-1].kind == "dry_run"
    b._pipeline.wait_for_frames.assert_not_called()
