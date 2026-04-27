from __future__ import annotations

import pytest

from robot_md.spatial_eval.probe.stacks import (
    BaselineClaudeStack,
    FakeStack,
    resolve_stack,
)


def test_fake_stack_returns_canned_answer():
    stack = FakeStack(answers={"o1-x": {"still_present": True, "position": [0, 0, 0]}})
    out = stack.answer({"id": "o1-x", "unit": "O1"})
    assert out == {"still_present": True, "position": [0, 0, 0]}


def test_resolve_stack_claude_only_in_v1():
    stack = resolve_stack("claude:claude-opus-4-7")
    assert isinstance(stack, BaselineClaudeStack)


def test_resolve_stack_rejects_non_claude_in_v1():
    with pytest.raises(ValueError, match="claude:"):
        resolve_stack("vla:my-endpoint")
