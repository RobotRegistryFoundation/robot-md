"""Anthropic planner shim — thin wrapper around the Messages API with tool use."""

from __future__ import annotations

import os
from typing import Callable


PLAN_TOOL = {
    "name": "emit_plan",
    "description": "Emit the full capability-step plan as a single structured response.",
    "input_schema": {
        "type": "object",
        "required": ["plan"],
        "properties": {
            "plan": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["capability", "args", "confidence"],
                    "properties": {
                        "capability": {"type": "string"},
                        "args": {"type": "object"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            }
        },
    },
}


def build_anthropic_client() -> Callable[[str, str, int], dict]:
    """Return a callable that takes (prompt, model, timeout_ms) → dict with `plan` key."""

    def _call(prompt: str, model: str, timeout_ms: int) -> dict:
        try:
            import anthropic
        except Exception as e:
            raise RuntimeError(f"anthropic SDK not installed: {e}")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            tools=[PLAN_TOOL],
            tool_choice={"type": "tool", "name": "emit_plan"},
            timeout=timeout_ms / 1000.0,
            messages=[{"role": "user", "content": prompt}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "emit_plan":
                return dict(block.input)
        raise RuntimeError("planner did not emit an emit_plan tool_use block")

    return _call
