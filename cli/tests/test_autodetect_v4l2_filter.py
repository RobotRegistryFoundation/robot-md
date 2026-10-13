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
    assert not any(m.startswith("pispbe") for m in models), (
        f"pispbe nodes leaked into camera list: {models}"
    )


def test_bare_pispbe_model_is_filtered():
    """v4l2-ctl on some Pi configs reports "pispbe" without the "-input" suffix.

    Bare-name matching previously slipped through (the old prefix included a
    trailing dash). This regression test pins the broadened semantics.
    """
    fake_paths = ["/dev/video0", "/dev/video20"]
    fake_caps = {
        "/dev/video0": {"model": "Logitech C920", "width": 1280, "height": 720},
        "/dev/video20": {"model": "pispbe", "width": 640, "height": 480},
    }
    with (
        patch("robot_md.autodetect._v4l2_list_devices", return_value=fake_paths),
        patch("robot_md.autodetect._v4l2_device_capabilities", side_effect=lambda p: fake_caps[p]),
    ):
        cams = probe_v4l2_cameras()
    models = [c.model for c in cams]
    assert "pispbe" not in models, f"bare pispbe node leaked: {models}"
    assert "Logitech C920" in models


def test_rpi_hevc_decoder_is_filtered():
    """Pi's HEVC hardware decoder shows up as a v4l2 device but is not a camera."""
    fake_paths = ["/dev/video0", "/dev/video19"]
    fake_caps = {
        "/dev/video0": {"model": "Logitech C920", "width": 1280, "height": 720},
        "/dev/video19": {"model": "rpi-hevc-dec", "width": 1920, "height": 1080},
    }
    with (
        patch("robot_md.autodetect._v4l2_list_devices", return_value=fake_paths),
        patch("robot_md.autodetect._v4l2_device_capabilities", side_effect=lambda p: fake_caps[p]),
    ):
        cams = probe_v4l2_cameras()
    models = [c.model for c in cams]
    assert "rpi-hevc-dec" not in models, f"HEVC decoder leaked into cameras: {models}"
    assert "Logitech C920" in models


def test_pisp_fe_frontend_is_filtered():
    """Pi 5 ISP front-end nodes (pisp-fe-*) are not cameras either."""
    fake_paths = ["/dev/video36"]
    fake_caps = {
        "/dev/video36": {"model": "pisp-fe-image", "width": 1920, "height": 1080},
    }
    with (
        patch("robot_md.autodetect._v4l2_list_devices", return_value=fake_paths),
        patch("robot_md.autodetect._v4l2_device_capabilities", side_effect=lambda p: fake_caps[p]),
    ):
        cams = probe_v4l2_cameras()
    assert cams == [], f"pisp-fe front-end nodes leaked: {[c.model for c in cams]}"
