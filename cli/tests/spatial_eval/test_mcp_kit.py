from __future__ import annotations
from unittest.mock import MagicMock
from robot_md.mcp.tools.spatial_eval.kit import kit_tool


def test_kit_returns_bom_text():
    out = kit_tool(MagicMock())
    assert out["ok"] is True
    assert "Standard kit" in out["bom_md"]
    assert out["grid_mat_pdf_path"].endswith("grid_mat.pdf")
