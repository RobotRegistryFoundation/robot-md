from __future__ import annotations

from robot_md.backends.base import SceneSnapshot
from robot_md.parser import parse_file
from robot_md.planning.prompt import build_prompt
from robot_md.robot_spec import RobotSpec


def test_prompt_includes_capabilities_and_user_task(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    spec = RobotSpec.from_parsed(parsed)
    prompt = build_prompt(
        spec=spec,
        scene=SceneSnapshot.empty(),
        user_prompt="pick the lego and place it to the left",
    )
    assert "arm.pick" in prompt
    assert "arm.place" in prompt
    assert "pick the lego" in prompt
    assert "Scene" in prompt


def test_prompt_includes_safety_workspace(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["safety"]["workspace_bounds_m"] = [0.5, 0.5, 0.4]
    parsed.frontmatter["safety"]["max_joint_velocity_dps"] = 180
    parsed.frontmatter["safety"]["payload_kg"] = 0.5
    spec = RobotSpec.from_parsed(parsed)
    prompt = build_prompt(spec=spec, scene=SceneSnapshot.empty(), user_prompt="do it")
    assert "0.5" in prompt
    assert "180" in prompt


def test_prompt_handles_empty_safety(fixtures_dir):
    """Minimal safety envelope still builds a valid prompt."""
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    # Remove safety fields that fixture now has to test empty safety case
    for field in ["max_joint_velocity_dps", "payload_kg", "workspace_bounds_m"]:
        if field in parsed.frontmatter["safety"]:
            del parsed.frontmatter["safety"][field]
    spec = RobotSpec.from_parsed(parsed)
    # spec now has no max_joint_velocity_dps/payload_kg/workspace_bounds_m
    prompt = build_prompt(spec=spec, scene=SceneSnapshot.empty(), user_prompt="x")
    assert "no safety limits declared" in prompt.lower()


def test_prompt_embeds_scene(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    spec = RobotSpec.from_parsed(parsed)
    scene = SceneSnapshot(
        frame=None,
        detections=({"class": "lego", "bbox": [0, 0, 10, 10], "conf": 0.9},),
        joint_state={"shoulder_pan": 0.0},
        ts=123.45,
    )
    prompt = build_prompt(spec=spec, scene=scene, user_prompt="x")
    assert "lego" in prompt
    assert "shoulder_pan" in prompt
