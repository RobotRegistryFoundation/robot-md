"""NL → capability plan decomposition pipeline."""

from __future__ import annotations

from typing import Callable

from robot_md.backends.base import SceneSnapshot
from robot_md.planning.prompt import build_prompt
from robot_md.planning.types import Plan, PlanError, PlanStep
from robot_md.robot_spec import RobotSpec


PlannerClient = Callable[[str, str, int], dict]


def decompose(
    *,
    spec: RobotSpec,
    scene: SceneSnapshot,
    user_prompt: str,
    client: PlannerClient | None = None,
) -> Plan:
    brain = spec.brain
    if brain is None or not brain.planning_model:
        raise PlanError("no_planner_declared", "spec.brain.planning is missing")

    if client is None:
        client = _build_default_client(brain.planning_provider or "anthropic")

    prompt = build_prompt(spec=spec, scene=scene, user_prompt=user_prompt)
    try:
        raw = client(prompt, brain.planning_model, brain.planning_timeout_ms)
    except TimeoutError as e:
        raise PlanError("timeout", str(e))
    except Exception as e:
        raise PlanError("planner_call_failed", str(e))

    raw_steps = raw.get("plan") if isinstance(raw, dict) else None
    if not isinstance(raw_steps, list):
        raise PlanError("malformed_plan", "plan field is not a list")

    steps: list[PlanStep] = []
    for i, s in enumerate(raw_steps):
        cap = s.get("capability") if isinstance(s, dict) else None
        if cap not in spec.capabilities:
            raise PlanError("unknown_capability", f"step {i}: '{cap}' not in declared capabilities")
        conf = float(s.get("confidence", 0.0))
        gate = brain.planning_confidence_gate
        if gate is not None and conf < gate:
            raise PlanError(
                "low_confidence",
                f"step {i}: '{cap}' confidence={conf:.2f} < gate={gate}",
            )
        steps.append(
            PlanStep(capability=cap, args=dict(s.get("args") or {}), confidence=conf)
        )
    return Plan(steps=tuple(steps), raw_response=raw)


def _build_default_client(provider: str) -> PlannerClient:
    if provider == "anthropic":
        from robot_md.planning.anthropic_shim import build_anthropic_client
        return build_anthropic_client()
    raise PlanError("unsupported_provider", f"provider '{provider}' not supported")
