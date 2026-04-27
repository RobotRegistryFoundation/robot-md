"""SP6 — JSON Schema tests for the `spatial-eval:` ROBOT.md frontmatter section.

The fixture below is a minimum-viable manifest: it satisfies every top-level
`required` field of the canonical `schema/v1/robot.schema.json` envelope so
that any validation failure is unambiguously caused by the spatial-eval
sub-tree (or its absence), not by missing top-level fields.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

# parents[0] = cli/tests/spatial_eval
# parents[1] = cli/tests
# parents[2] = cli
# parents[3] = worktree root  →  schema/v1/robot.schema.json (canonical)
SCHEMA = json.loads(
    (Path(__file__).resolve().parents[3] / "schema/v1/robot.schema.json").read_text()
)

VALID_MIN: dict = {
    "rcan_version": "3.2",
    "metadata": {"robot_name": "test-robot"},
    "physics": {"type": "sensor", "dof": 0},
    "drivers": [{"id": "fs", "protocol": "composite"}],
    "safety": {"estop": {"software": True, "response_ms": 50}},
    "spatial-eval": {
        "spec_version": "1.0.0",
        "units": ["O1", "O2", "O3", "A1", "A2"],
        "workspace": {
            "play_surface_dims_m": [0.30, 0.30],
            "judge_camera": {"device": "phone:tripod", "resolution": [1920, 1080]},
        },
        "reasoning_stack": {
            "baseline": "claude:claude-opus-4-7",
            "declared": "claude:claude-opus-4-7",
        },
    },
}


def test_spatial_eval_section_validates() -> None:
    Draft202012Validator(SCHEMA).validate(VALID_MIN)


def test_spatial_eval_rejects_non_claude_stack_in_v1() -> None:
    bad = copy.deepcopy(VALID_MIN)
    bad["spatial-eval"]["reasoning_stack"]["declared"] = "vla:my-endpoint"
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(bad)


def test_spatial_eval_rejects_unknown_unit() -> None:
    bad = copy.deepcopy(VALID_MIN)
    bad["spatial-eval"]["units"] = ["O1", "X9"]
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(bad)


def test_spatial_eval_section_is_optional() -> None:
    no_eval = copy.deepcopy(VALID_MIN)
    del no_eval["spatial-eval"]
    Draft202012Validator(SCHEMA).validate(no_eval)
