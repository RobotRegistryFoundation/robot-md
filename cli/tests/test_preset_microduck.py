"""The microduck preset: loads, validates, and `init --preset microduck` writes a valid ROBOT.md."""

from __future__ import annotations

import math
from typing import ClassVar

import jsonschema
import pytest

from robot_md.init import load_presets, merge_preset_into_draft, non_interactive
from robot_md.validate import _load_schema

SKILLS = {"skill.kick_left", "skill.kick_right", "skill.roulade", "skill.ground_pick"}


class _Scan:
    devices: ClassVar[list] = []
    cameras: ClassVar[list] = []


@pytest.fixture
def duck():
    return next(p for p in load_presets() if p.name == "microduck")


def test_microduck_frontmatter_validates_against_schema(duck):
    fm = merge_preset_into_draft(duck, "duck", _Scan())
    jsonschema.Draft202012Validator(_load_schema()).validate(fm)


def test_microduck_declares_the_closed_skill_set(duck):
    caps = set(duck.data["capabilities"])
    assert caps >= SKILLS
    assert caps >= {"move.walk", "move.turn", "sound.play", "status.report"}
    # Head motion is not declared until it has its own envelope rows.
    assert not any(c.startswith("head.") for c in caps)


def test_microduck_motion_scopes_require_auth(duck):
    gates = {g["scope"]: g["require_auth"] for g in duck.data["safety"]["hitl_gates"]}
    assert gates["move"] is True
    assert gates["skill"] is True
    assert gates["sound"] is False


def test_microduck_envelope_agrees_with_top_level_limits(duck):
    safety = duck.data["safety"]
    env = safety["envelope"]
    linear = max(env["max_forward_ms"], env["max_backward_ms"], env["max_sideways_ms"])
    assert safety["max_linear_velocity_ms"] == linear == 0.3
    assert env["max_turn_rads"] == 1.0
    assert safety["max_angular_velocity_dps"] == pytest.approx(math.degrees(1.0), abs=0.05)
    assert "hardware" not in safety["estop"], "no hardware stop is sourced for the duck"


def test_microduck_init_does_not_add_arm_defaults(duck):
    fm = merge_preset_into_draft(duck, "duck", _Scan())
    # robotd is not an actuation protocol robot-md drives, and nothing here picks.
    assert "max_joint_velocity_dps" not in fm["safety"]
    assert "vision" not in fm


def test_init_preset_microduck_writes_valid_robot_md(tmp_path):
    from robot_md.parser import parse_file
    from robot_md.validate import VALID
    from robot_md.validate import validate as validate_parsed

    out = tmp_path / "ROBOT.md"
    rc = non_interactive(out, robot_name="duck", preset_name="microduck", force=True)
    assert rc == 0
    result = validate_parsed(parse_file(out))
    assert result.code == VALID, result
    text = out.read_text()
    assert "not affiliated with Pollen" in text
