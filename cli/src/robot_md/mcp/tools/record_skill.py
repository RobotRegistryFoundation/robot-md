"""MCP tool: append/upsert a learned_skills[] entry on the manifest."""

from __future__ import annotations

import datetime as _dt
from typing import Any

import yaml

from robot_md.parser import parse_file


def record_skill_tool(
    ctx: Any,
    *,
    skill_id: str,
    status: str = "ok",
    validated: list[str] | None = None,
    blocked_by: list[str] | None = None,
    notes: str | None = None,
) -> dict:
    """Append or upsert (by id) a learned_skills entry on the manifest.

    Preserves prose body. Sets recorded_at to today's ISO date.
    """
    path = ctx.manifest_path
    parsed = parse_file(path)
    fm = dict(parsed.frontmatter)
    ls = list(fm.get("learned_skills") or [])
    entry: dict[str, Any] = {
        "id": skill_id,
        "status": status,
        "validated": list(validated or []),
        "blocked_by": list(blocked_by or []),
        "recorded_at": _dt.date.today().isoformat(),
    }
    if notes:
        entry["notes"] = notes

    for i, existing in enumerate(ls):
        if isinstance(existing, dict) and existing.get("id") == skill_id:
            ls[i] = entry
            break
    else:
        ls.append(entry)
    fm["learned_skills"] = ls

    path.write_text("---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + parsed.body)
    return {"status": "ok", "skill_id": skill_id, "count": len(ls)}
