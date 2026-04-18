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


def test_legacy_upgrade_fallback_to_literal_camera_id(tmp_path):
    """When no camera-protocol driver exists, fallback driver_id is literal 'camera'."""
    robot_md = tmp_path / "fallback.ROBOT.md"
    robot_md.write_text(
        "---\n"
        "rcan_version: \"3.0\"\n"
        "metadata: {robot_name: t}\n"
        "physics:\n"
        "  type: arm\n"
        "  dof: 1\n"
        "  solver:\n"
        "    camera:\n"
        "      mount: world\n"
        "      extrinsic: null\n"
        "drivers:\n"
        "  - {id: arm_servos, protocol: feetech, port: /dev/ttyACM0, count: 1}\n"
        "safety:\n"
        "  estop: {software: true, response_ms: 100}\n"
        "---\n\n"
        "# t\n\n## Identity\n\nx\n\n"
        "## What t Can Do\n\nx\n\n## Safety Gates\n\nx\n"
    )
    from robot_md.parser import parse_file
    parsed = parse_file(robot_md)
    cams = parsed.frontmatter["physics"]["solver"]["cameras"]
    assert len(cams) == 1
    assert cams[0]["driver_id"] == "camera"
