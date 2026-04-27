"""MCP tool: spatial_eval_kit — return BOM markdown + grid mat PDF path."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[3] / "spatial_eval/execute/fixtures"


def kit_tool(ctx) -> dict:
    bom_path = FIXTURES / "kit_v1.md"
    pdf_path = FIXTURES / "grid_mat.pdf"
    return {
        "ok": True,
        "bom_md": bom_path.read_text() if bom_path.is_file() else "",
        "grid_mat_pdf_path": str(pdf_path),
    }
