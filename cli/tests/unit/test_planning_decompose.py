from __future__ import annotations

import pytest

from robot_md.backends.base import SceneSnapshot
from robot_md.parser import parse_file
from robot_md.planning.decompose import decompose
from robot_md.planning.types import PlanError
from robot_md.robot_spec import RobotSpec


def _spec_with_planner(fixtures_dir, **planner):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["brain"] = {"planning": planner}
    return RobotSpec.from_parsed(parsed)


def test_rejects_hallucinated_capability(fixtures_dir):
    spec = _spec_with_planner(
        fixtures_dir, provider="anthropic", model="claude-opus-4-7", confidence_gate=0.6
    )

    def fake(prompt, model, timeout_ms):
        return {"plan": [{"capability": "arm.throw", "args": {}, "confidence": 0.9}]}

    with pytest.raises(PlanError) as ei:
        decompose(spec=spec, scene=SceneSnapshot.empty(), user_prompt="throw it", client=fake)
    assert ei.value.reason == "unknown_capability"


def test_rejects_low_confidence(fixtures_dir):
    spec = _spec_with_planner(
        fixtures_dir, provider="anthropic", model="claude-opus-4-7", confidence_gate=0.6
    )

    def fake(prompt, model, timeout_ms):
        return {"plan": [{"capability": "arm.pick", "args": {"object": "lego"}, "confidence": 0.3}]}

    with pytest.raises(PlanError) as ei:
        decompose(spec=spec, scene=SceneSnapshot.empty(), user_prompt="pick lego", client=fake)
    assert ei.value.reason == "low_confidence"


def test_accepts_valid_plan(fixtures_dir):
    spec = _spec_with_planner(
        fixtures_dir, provider="anthropic", model="claude-opus-4-7", confidence_gate=0.6
    )

    def fake(prompt, model, timeout_ms):
        return {
            "plan": [
                {"capability": "arm.pick", "args": {"object": "lego"}, "confidence": 0.9},
                {"capability": "arm.place", "args": {"pose": {"x": 0.1}}, "confidence": 0.8},
            ]
        }

    plan = decompose(spec=spec, scene=SceneSnapshot.empty(), user_prompt="pick+place", client=fake)
    assert len(plan.steps) == 2
    assert plan.steps[0].capability == "arm.pick"
    assert plan.steps[0].args == {"object": "lego"}
    assert plan.steps[0].confidence == 0.9


def test_no_planner_declared_raises(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    spec = RobotSpec.from_parsed(parsed)  # no brain block
    with pytest.raises(PlanError) as ei:
        decompose(spec=spec, scene=SceneSnapshot.empty(), user_prompt="x", client=None)
    assert ei.value.reason == "no_planner_declared"


def test_malformed_plan_raises(fixtures_dir):
    spec = _spec_with_planner(
        fixtures_dir, provider="anthropic", model="claude-opus-4-7", confidence_gate=0.6
    )

    def fake(prompt, model, timeout_ms):
        return {"plan": "not-a-list"}

    with pytest.raises(PlanError) as ei:
        decompose(spec=spec, scene=SceneSnapshot.empty(), user_prompt="x", client=fake)
    assert ei.value.reason == "malformed_plan"


def test_planner_call_failure_wrapped(fixtures_dir):
    spec = _spec_with_planner(
        fixtures_dir, provider="anthropic", model="claude-opus-4-7", confidence_gate=0.6
    )

    def boom(prompt, model, timeout_ms):
        raise RuntimeError("network down")

    with pytest.raises(PlanError) as ei:
        decompose(spec=spec, scene=SceneSnapshot.empty(), user_prompt="x", client=boom)
    assert ei.value.reason == "planner_call_failed"
