"""Shared helpers for spatial_eval MCP tools.

Provides shape-tolerant access to the manifest frontmatter on `ctx.parsed`.

Production `McpContext.parsed` is a `ParsedRobotMd` dataclass with a
`.frontmatter: dict` attribute. Tests sometimes assign `ctx.parsed = {...}`
directly (a bare dict). This helper accepts either shape so test churn is
minimized while production behavior is correct.
"""

from __future__ import annotations

from typing import Any


def _frontmatter(ctx: Any) -> dict:
    """Return the manifest frontmatter dict regardless of ctx.parsed shape.

    - Production: `ctx.parsed` is a `ParsedRobotMd` with `.frontmatter: dict`.
    - Tests: `ctx.parsed` is sometimes assigned a bare `dict`.
    - Missing: returns an empty dict so callers can `.get(...)` safely.
    """
    parsed = getattr(ctx, "parsed", None)
    if parsed is None:
        return {}
    fm = getattr(parsed, "frontmatter", None)
    if isinstance(fm, dict):
        return fm
    if isinstance(parsed, dict):
        return parsed
    return {}
