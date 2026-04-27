"""MCP tool: spatial_eval_init — scaffold spatial-eval block into ROBOT.md."""

from __future__ import annotations

from pathlib import Path

DEFAULT_BLOCK = """spatial-eval:
  spec_version: "1.0.0"
  units: {units_yaml}
  workspace:
    play_surface_dims_m: [0.30, 0.30]
    judge_camera:
      device: "phone:tripod"
      resolution: [1920, 1080]
  reasoning_stack:
    baseline: "claude:claude-opus-4-7"
    declared: "claude:claude-opus-4-7"
"""


def init_tool(ctx, *, units: list[str]) -> dict:
    mp = getattr(ctx, "manifest_path", None)
    if mp is None:
        return {"ok": False, "error": "ctx.manifest_path not set"}
    f: Path = Path(mp)
    text = f.read_text()
    if "spatial-eval:" in text:
        return {"ok": True, "status": "already_present"}
    units_yaml = "[" + ", ".join(units) + "]"
    block = DEFAULT_BLOCK.format(units_yaml=units_yaml)
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end == -1:
            return {"ok": False, "error": "ROBOT.md frontmatter unterminated"}
        f.write_text(text[: end + 1] + block + text[end + 1 :])
    else:
        f.write_text(text.rstrip() + "\n\n" + block)
    return {"ok": True, "status": "added", "units": units}
