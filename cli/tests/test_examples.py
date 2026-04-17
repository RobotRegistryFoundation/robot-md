"""Conformance: every shipped example must validate cleanly."""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_md.parser import parse_file
from robot_md.validate import VALID, validate

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"
REPO_ROOT = Path(__file__).parent.parent.parent


def _example_files():
    yield from EXAMPLES_DIR.glob("*.ROBOT.md")
    root_robot_md = REPO_ROOT / "ROBOT.md"
    if root_robot_md.exists():
        yield root_robot_md


@pytest.mark.parametrize("example", list(_example_files()), ids=lambda p: p.name)
def test_example_validates(example):
    parsed = parse_file(example)
    result = validate(parsed)
    assert result.code == VALID, f"{example.name} failed validation: errors={result.errors}"
