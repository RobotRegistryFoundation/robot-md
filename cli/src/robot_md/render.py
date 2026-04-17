"""Render a parsed ROBOT.md's frontmatter as pure YAML (strip prose)."""

from __future__ import annotations

import yaml

from robot_md.parser import ParsedRobotMd


def render_yaml(parsed: ParsedRobotMd) -> str:
    """Emit the frontmatter dict as block-style YAML, no delimiters, no prose."""
    return yaml.safe_dump(
        parsed.frontmatter,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
