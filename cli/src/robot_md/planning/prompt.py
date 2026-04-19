"""Build the planner prompt from spec + scene + user prompt."""

from __future__ import annotations

import json

from robot_md.backends.base import SceneSnapshot
from robot_md.robot_spec import RobotSpec

SYSTEM = """\
You are the planner for robot `{robot_name}` ({physics_type}, {dof} DoF).

Decompose the user's task into a sequence of capability calls drawn from
the declared capability set. Return STRICT JSON matching the tool
schema; never invent capabilities. Include a confidence score in [0, 1]
per step; below the declared confidence_gate the step is rejected.
"""

USER = """\
## Declared capabilities (allowed)
{capabilities}

## Safety envelope
{safety}

## Scene (current)
{scene}

## User task
{user_prompt}
"""


def build_prompt(*, spec: RobotSpec, scene: SceneSnapshot, user_prompt: str) -> str:
    caps = "\n".join(f"- {c}" for c in sorted(spec.capabilities))
    safety_lines: list[str] = []
    if spec.safety.max_joint_velocity_dps is not None:
        safety_lines.append(f"- max_joint_velocity_dps: {spec.safety.max_joint_velocity_dps}")
    if spec.safety.payload_kg is not None:
        safety_lines.append(f"- payload_kg: {spec.safety.payload_kg}")
    if spec.safety.workspace_bounds_m is not None:
        safety_lines.append(f"- workspace_bounds_m: {list(spec.safety.workspace_bounds_m)}")
    for gate in spec.safety.hitl_gates:
        safety_lines.append(f"- hitl_gate: {gate}")
    safety_str = "\n".join(safety_lines) or "(no safety limits declared)"

    scene_obj = {
        "detections": list(scene.detections),
        "joint_state": scene.joint_state,
        "ts": scene.ts,
    }

    system = SYSTEM.format(
        robot_name=spec.metadata.robot_name,
        physics_type=spec.physics.type,
        dof=spec.physics.dof,
    )
    user = USER.format(
        capabilities=caps,
        safety=safety_str,
        scene=json.dumps(scene_obj, indent=2),
        user_prompt=user_prompt,
    )
    return system + "\n\n" + user
