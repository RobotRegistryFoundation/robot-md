from __future__ import annotations

from pathlib import Path

import yaml

_PRESETS_DIR = Path(__file__).parents[2] / "src" / "robot_md" / "presets"


def _load(preset: str) -> dict:
    return yaml.safe_load((_PRESETS_DIR / preset).read_text())


def _arm_driver_of(data: dict) -> dict:
    for drv in data.get("drivers", []):
        if drv.get("protocol") in {"feetech", "dynamixel"}:
            return drv
    raise AssertionError(f"no arm driver in preset: {data}")


def test_so_arm_presets_prefer_lerobot() -> None:
    for preset in ("so_arm101.yaml", "so_arm101_leader.yaml", "koch_arm.yaml", "aloha2.yaml"):
        data = _load(preset)
        arm = _arm_driver_of(data)
        assert arm.get("preferred_backend") == "lerobot", (
            f"{preset} arm driver missing or wrong preferred_backend "
            f"(got {arm.get('preferred_backend')!r})"
        )
