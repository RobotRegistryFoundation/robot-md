"""Tests for `robot-md init` — preset library, matcher, and merge."""
# ruff: noqa: RUF012  (test-local duck-typed Scan/Device classes; mutable defaults are fine)

from __future__ import annotations

import pytest

from robot_md.init import (
    PRESETS_DIR,
    Preset,
    load_presets,
    match_score,
    merge_preset_into_draft,
    non_interactive,
    pick_best,
    render_draft,
)


@pytest.fixture
def presets() -> list[Preset]:
    return load_presets()


def test_loads_shipped_presets(presets):
    names = {p.name for p in presets}
    # Minimal v1.1 set
    for expected in ("so_arm101", "so_arm101_leader", "turtlebot4", "picar_x", "minimal"):
        assert expected in names, f"shipped preset {expected!r} missing"


def test_every_shipped_preset_has_physics(presets):
    for p in presets:
        assert "physics" in p.data, f"{p.name} missing physics block"
        assert "type" in p.data["physics"]


def test_preset_match_score_for_so_arm101(presets):
    """A fake scan with a Feetech serial device should match so-arm101 strongly."""

    class Device:
        def __init__(self, bus=None, protocol=None, label="", path=None):
            self.bus = bus
            self.protocol = protocol
            self.label = label
            self.path = path

    class Scan:
        def __init__(self, devices):
            self.devices = devices

    scan = Scan(
        [Device(bus="usb", protocol="feetech", label="Feetech servo bus", path="/dev/ttyACM0")]
    )
    so = next(p for p in presets if p.name == "so_arm101")
    r = match_score(so, scan)
    assert r.score >= 10
    assert any("protocol" in reason for reason in r.reasons)


def test_preset_match_score_zero_on_empty_scan(presets):
    class Scan:
        devices = []

    scan = Scan()
    so = next(p for p in presets if p.name == "so_arm101")
    assert match_score(so, scan).score == 0


def test_pick_best_returns_highest(presets):
    class Device:
        bus = "usb"
        protocol = "feetech"
        label = ""
        path = "/dev/ttyACM0"

    class Scan:
        devices = [Device()]

    r = pick_best(presets, Scan())
    assert r is not None
    assert r.preset.name == "so_arm101"  # highest scorer on a Feetech bus


def test_pick_best_prefers_minimal_when_all_scores_zero(presets):
    """When nothing matches (e.g. headless CI with no hardware), the
    empty-match `minimal` preset is the semantically correct fallback.
    Without this tie-break, alphabetical ordering gives the operator
    `aloha2.yaml` for a machine with no Dynamixel arm — confusing.
    """

    class Scan:
        devices = []

    r = pick_best(presets, Scan())
    assert r is not None
    assert r.preset.name == "minimal", f"expected minimal on all-zero scan, got {r.preset.name}"
    assert r.score == 0


def test_merge_populates_identity_and_physics(presets):
    so = next(p for p in presets if p.name == "so_arm101")

    class Scan:
        devices = []

    fm = merge_preset_into_draft(so, "bob", Scan())
    assert fm["metadata"]["robot_name"] == "bob"
    assert fm["rcan_version"] == "3.0"
    assert fm["physics"]["type"] == "arm"
    assert len(fm["physics"]["kinematics"]) == 6
    # Preset's driver declaration should carry through
    assert fm["drivers"][0]["protocol"] == "feetech"


def test_merge_overrides_port_with_scan(presets):
    so = next(p for p in presets if p.name == "so_arm101")

    class Device:
        bus = "usb"
        protocol = "feetech"
        label = ""
        path = "/dev/ttyUSB7"  # unusual port — scan wins

    class Scan:
        devices = [Device()]

    fm = merge_preset_into_draft(so, "bob", Scan())
    assert fm["drivers"][0]["port"] == "/dev/ttyUSB7"


def test_render_draft_contains_frontmatter_and_body(presets):
    so = next(p for p in presets if p.name == "so_arm101")

    class Scan:
        devices = []

    fm = merge_preset_into_draft(so, "bob", Scan())
    text = render_draft(fm, so.data.get("body_hints"))
    assert text.startswith("---\n")
    assert "rcan_version" in text
    assert "# bob" in text
    assert "## Identity" in text
    assert "## What bob Can Do" in text
    assert "## Safety Gates" in text


def test_non_interactive_writes_valid_minimal_draft(tmp_path):
    from robot_md.parser import parse_file
    from robot_md.validate import VALID
    from robot_md.validate import validate as validate_parsed

    out = tmp_path / "ROBOT.md"
    rc = non_interactive(out, robot_name="test-bot", preset_name="minimal", force=True)
    assert rc == 0
    assert out.exists()
    parsed = parse_file(out)
    result = validate_parsed(parsed)
    assert result.code == VALID


def test_non_interactive_writes_valid_so_arm101_draft(tmp_path):
    from robot_md.parser import parse_file
    from robot_md.validate import VALID
    from robot_md.validate import validate as validate_parsed

    out = tmp_path / "ROBOT.md"
    rc = non_interactive(out, robot_name="test-arm", preset_name="so-arm101", force=True)
    assert rc == 0
    parsed = parse_file(out)
    result = validate_parsed(parsed)
    assert result.code == VALID


def test_quick_alias_still_works_with_warning(tmp_path, capsys):
    from robot_md.init import quick

    out = tmp_path / "ROBOT.md"
    rc = quick(out, robot_name="bob", preset_name="minimal", force=True)
    assert rc == 0
    err = capsys.readouterr().err
    assert "deprecated" in err.lower() or "non_interactive" in err.lower()


def test_quick_refuses_overwrite_without_force(tmp_path):
    out = tmp_path / "ROBOT.md"
    out.write_text("existing content\n")
    rc = non_interactive(out, robot_name="x", preset_name="minimal", force=False)
    assert rc == 2
    assert out.read_text() == "existing content\n"


def test_quick_allows_overwrite_with_force(tmp_path):
    out = tmp_path / "ROBOT.md"
    out.write_text("existing\n")
    rc = non_interactive(out, robot_name="x", preset_name="minimal", force=True)
    assert rc == 0
    assert out.read_text() != "existing\n"


def test_presets_dir_is_in_package():
    """Presets ship with the installed package (not just the repo root)."""
    assert PRESETS_DIR.exists()
    assert any(PRESETS_DIR.glob("*.yaml"))


def test_unknown_preset_name_fails_cleanly(tmp_path):
    out = tmp_path / "ROBOT.md"
    rc = non_interactive(out, robot_name="x", preset_name="not-a-real-preset", force=True)
    assert rc != 0
    assert not out.exists()


def test_so_arm101_preset_ships_object_descriptors(presets):
    """Preset so_arm101 declares red_lego + white_bowl by default."""
    so = next(p for p in presets if p.name == "so_arm101")
    vision = so.data.get("vision") or {}
    descs = vision.get("object_descriptors") or []
    ids = {d["id"] for d in descs}
    assert "red_lego" in ids, f"missing red_lego; have {ids}"
    assert "white_bowl" in ids, f"missing white_bowl; have {ids}"
    # Spot-check shape: each declares a detector + params.
    red = next(d for d in descs if d["id"] == "red_lego")
    assert red["detector"] == "hsv"
    assert "h_ranges" in red["params"]
    bowl = next(d for d in descs if d["id"] == "white_bowl")
    assert bowl["detector"] == "hsv_roi"
    assert "roi" in bowl["params"]
