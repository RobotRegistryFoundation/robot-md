from __future__ import annotations

from robot_md.parser import parse_file
from robot_md.validate import validate


def test_cameras_driver_id_must_resolve(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_no_intrinsic.yaml")
    result = validate(parsed)
    assert any("driver_id" in e and "does-not-exist" in e for e in result.errors)


def test_null_primary_stream_intrinsic_warns(fixtures_dir):
    """Primary stream with null intrinsic is a WARNING, not an error."""
    parsed = parse_file(fixtures_dir / "robot_md_no_intrinsic.yaml")
    parsed.frontmatter["physics"]["solver"]["cameras"][0]["driver_id"] = "oak-d-1"
    result = validate(parsed)
    assert not any("driver_id" in e for e in result.errors)
    assert any("primary_stream" in w and "null" in w.lower() for w in result.warnings)
