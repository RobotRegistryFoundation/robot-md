from __future__ import annotations

from robot_md.parser import parse_file
from robot_md.validate import validate


def test_legacy_singular_camera_autoupgraded(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_legacy_camera_singular.yaml")
    cams = parsed.frontmatter["physics"]["solver"].get("cameras")
    assert cams is not None and len(cams) == 1
    assert "camera" not in parsed.frontmatter["physics"]["solver"]


def test_legacy_singular_camera_emits_deprecation_warning(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_legacy_camera_singular.yaml")
    result = validate(parsed)
    assert any(
        "deprecat" in w.lower() and "camera" in w.lower() for w in result.warnings
    )


def test_legacy_upgrade_sets_driver_id_from_camera_protocol(fixtures_dir):
    """When a driver with protocol 'depthai'/'realsense'/'v4l2'/'zed'/'uvc' exists,
    the auto-upgraded cameras[0].driver_id points at it."""
    parsed = parse_file(fixtures_dir / "robot_md_legacy_camera_singular.yaml")
    cam = parsed.frontmatter["physics"]["solver"]["cameras"][0]
    assert cam["driver_id"] == "oak-d-1"
    assert cam["primary_stream"] == "rgb"
    assert cam["mount"] == "world"
    assert cam["extrinsic"] is None
