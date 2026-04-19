from __future__ import annotations

import json

import pytest

from robot_md.calibrate_intrinsic import (
    session_add_frame,
    session_finalize,
    session_init,
)


def test_init_creates_checkerboard_and_session(tmp_path):
    session_file = tmp_path / "intrinsic.session.json"
    session_init(
        session_file=session_file,
        driver_id="oak-d-1",
        stream="rgb",
        board_size=(9, 6),
    )
    data = json.loads(session_file.read_text())
    assert data["complete"] is False
    assert data["frames_captured"] == 0
    assert data["driver_id"] == "oak-d-1"
    assert data["stream"] == "rgb"
    assert (tmp_path / "checkerboard_9x6.png").exists()


def test_add_frame_updates_progress(tmp_path, monkeypatch):
    session_file = tmp_path / "intrinsic.session.json"
    session_init(session_file=session_file, driver_id="oak-d-1", stream="rgb", board_size=(9, 6))

    import robot_md.calibrate_intrinsic as m

    monkeypatch.setattr(
        m, "_detect_corners", lambda img, size: (True, [[0, 0]] * (size[0] * size[1]))
    )
    monkeypatch.setattr(m, "_load_image", lambda p: b"fake-img")

    session_add_frame(session_file=session_file, frame_path=tmp_path / "frame1.png")
    data = json.loads(session_file.read_text())
    assert data["frames_captured"] == 1


def test_add_frame_records_no_detection(tmp_path, monkeypatch):
    """When detection fails, frames_captured stays the same and next_hint coaches the user."""
    session_file = tmp_path / "intrinsic.session.json"
    session_init(session_file=session_file, driver_id="oak-d-1", stream="rgb", board_size=(9, 6))

    import robot_md.calibrate_intrinsic as m

    monkeypatch.setattr(m, "_detect_corners", lambda img, size: (False, None))
    monkeypatch.setattr(m, "_load_image", lambda p: b"fake-img")

    session_add_frame(session_file=session_file, frame_path=tmp_path / "bad.png")
    data = json.loads(session_file.read_text())
    assert data["frames_captured"] == 0
    assert "checkerboard" in data["next_hint"].lower() or "detect" in data["next_hint"].lower()


def test_finalize_writes_intrinsic_into_robot_md(tmp_path, monkeypatch, fixtures_dir):
    robot_md_file = tmp_path / "bob.ROBOT.md"
    robot_md_file.write_text((fixtures_dir / "robot_md_oak_d_factory_cal.yaml").read_text())
    session_file = tmp_path / "intrinsic.session.json"
    session_init(session_file=session_file, driver_id="oak-d-1", stream="rgb", board_size=(9, 6))

    import robot_md.calibrate_intrinsic as m

    monkeypatch.setattr(
        m,
        "_calibrate",
        lambda frames, size: {
            "fx": 800.0,
            "fy": 800.0,
            "cx": 320.0,
            "cy": 240.0,
            "width": 640,
            "height": 480,
            "distortion_model": "plumb_bob",
            "distortion_coeffs": [0.0, 0.0, 0.0, 0.0, 0.0],
            "rms_error": 0.3,
        },
    )
    # Pre-populate enough frames so finalize doesn't complain about too few
    data = json.loads(session_file.read_text())
    data["frames_captured"] = 10
    data["_frames"] = [str(tmp_path / "f.png")] * 10
    session_file.write_text(json.dumps(data))

    session_finalize(session_file=session_file, robot_md_file=robot_md_file)

    import yaml

    content = robot_md_file.read_text()
    fm = yaml.safe_load(content.split("---")[1])
    drv = next(d for d in fm["drivers"] if d["id"] == "oak-d-1")
    intr = drv["streams"]["rgb"]["intrinsic"]
    assert intr["fx"] == 800.0
    assert intr["distortion_model"] == "plumb_bob"

    # Session gets marked complete with rms_error recorded
    data_after = json.loads(session_file.read_text())
    assert data_after["complete"] is True
    assert data_after["rms_error"] == 0.3


def test_finalize_refuses_if_too_few_frames(tmp_path, fixtures_dir):
    robot_md_file = tmp_path / "bob.ROBOT.md"
    robot_md_file.write_text((fixtures_dir / "robot_md_oak_d_factory_cal.yaml").read_text())
    session_file = tmp_path / "intrinsic.session.json"
    session_init(session_file=session_file, driver_id="oak-d-1", stream="rgb", board_size=(9, 6))

    with pytest.raises(RuntimeError, match="frames"):
        session_finalize(session_file=session_file, robot_md_file=robot_md_file)
