from unittest.mock import patch

from robot_md.autodetect import probe_v4l2_cameras


def test_pispbe_video_nodes_are_filtered():
    """Pi ISP probe nodes (pispbe-*) should not appear as cameras."""
    fake_paths = [
        "/dev/video0",  # real USB cam
        "/dev/video19",  # pispbe-input
        "/dev/video20",  # pispbe-tdn-input
        "/dev/video21",  # pispbe-stitch-input
    ]
    fake_caps = {
        "/dev/video0": {"model": "Logitech C920", "width": 1280, "height": 720},
        "/dev/video19": {"model": "pispbe-input", "width": 640, "height": 480},
        "/dev/video20": {"model": "pispbe-tdn-input", "width": 640, "height": 480},
        "/dev/video21": {"model": "pispbe-stitch-input", "width": 640, "height": 480},
    }

    with (
        patch("robot_md.autodetect._v4l2_list_devices", return_value=fake_paths),
        patch("robot_md.autodetect._v4l2_device_capabilities", side_effect=lambda p: fake_caps[p]),
    ):
        cams = probe_v4l2_cameras()

    models = [c.model for c in cams]
    assert "Logitech C920" in models
    assert not any(m.startswith("pispbe-") for m in models), (
        f"pispbe-* nodes leaked into camera list: {models}"
    )
