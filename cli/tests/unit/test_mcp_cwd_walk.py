"""find_manifest_via_cwd_walk locates ROBOT.md by walking up from a starting dir."""

from __future__ import annotations

from pathlib import Path

from robot_md.mcp.server import find_manifest_via_cwd_walk


def test_finds_manifest_in_start_dir(tmp_path: Path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: x\n---\n# x\n")
    assert find_manifest_via_cwd_walk(tmp_path) == manifest


def test_finds_manifest_in_parent(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "ROBOT.md").write_text("---\nmetadata:\n  robot_name: x\n---\n# x\n")
    nested = project / "subdir" / "deeper"
    nested.mkdir(parents=True)
    assert find_manifest_via_cwd_walk(nested) == project / "ROBOT.md"


def test_returns_none_when_not_found(tmp_path: Path):
    nested = tmp_path / "subdir"
    nested.mkdir()
    assert find_manifest_via_cwd_walk(nested) is None


def test_picks_closest_when_nested_manifests_exist(tmp_path: Path):
    """Nearest ancestor wins."""
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    (outer / "ROBOT.md").write_text("---\nmetadata:\n  robot_name: outer\n---\n")
    (inner / "ROBOT.md").write_text("---\nmetadata:\n  robot_name: inner\n---\n")
    deepest = inner / "subdir"
    deepest.mkdir()
    assert find_manifest_via_cwd_walk(deepest) == inner / "ROBOT.md"


def test_stops_at_filesystem_root(tmp_path: Path):
    """Doesn't walk past the root."""
    # tmp_path is unique; if we don't bottom out, we walk all the way to /
    # and the test takes forever or crashes. The function must terminate.
    assert find_manifest_via_cwd_walk(Path("/")) is None  # safe — / has no ROBOT.md
