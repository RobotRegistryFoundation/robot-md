from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from robot_md.mcp.tools.spatial_eval.init import init_tool

ROBOT_MD_TEMPLATE = """---
robot-md: "1.0.0"
id: bob
kind: tabletop_arm
---
"""


def test_init_adds_spatial_eval_block(tmp_path: Path):
    f = tmp_path / "ROBOT.md"
    f.write_text(ROBOT_MD_TEMPLATE)
    ctx = MagicMock()
    ctx.manifest_path = f
    out = init_tool(ctx, units=["O1", "O2"])
    assert out["ok"] is True
    text = f.read_text()
    assert "spatial-eval:" in text
    assert 'spec_version: "1.0.0"' in text
    assert "O1" in text and "O2" in text


def test_init_idempotent(tmp_path: Path):
    f = tmp_path / "ROBOT.md"
    f.write_text(ROBOT_MD_TEMPLATE)
    ctx = MagicMock()
    ctx.manifest_path = f
    init_tool(ctx, units=["O1"])
    out = init_tool(ctx, units=["O1"])
    assert out["ok"] is True
    assert f.read_text().count("spatial-eval:") == 1
