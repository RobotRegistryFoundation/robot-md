from __future__ import annotations

from pathlib import Path

import pytest
import yaml

PRESETS = Path(__file__).parents[2] / "src" / "robot_md" / "presets"


@pytest.mark.parametrize("preset", sorted(PRESETS.glob("*.yaml")), ids=lambda p: p.name)
def test_preset_has_no_legacy_singular_camera(preset):
    data = yaml.safe_load(preset.read_text())
    solver = ((data or {}).get("physics") or {}).get("solver") or {}
    assert "camera" not in solver, f"{preset.name} still uses singular `camera:`"


@pytest.mark.parametrize("preset", sorted(PRESETS.glob("*.yaml")), ids=lambda p: p.name)
def test_preset_cameras_is_valid_if_present(preset):
    data = yaml.safe_load(preset.read_text())
    solver = ((data or {}).get("physics") or {}).get("solver") or {}
    cams = solver.get("cameras")
    if cams is None:
        return
    assert isinstance(cams, list)
    for cam in cams:
        assert cam.get("driver_id"), f"{preset.name} cameras[] entry missing driver_id"
        assert cam.get("primary_stream") in {
            "rgb",
            "left",
            "right",
            "depth",
            "mono",
            "ir",
            "thermal",
        }, f"{preset.name} cameras[].primary_stream invalid"
        assert "mount" in cam
