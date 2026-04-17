"""Parse a ROBOT.md file into frontmatter (dict) and body (markdown string)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import frontmatter
import yaml


class ParseError(Exception):
    """Raised when a ROBOT.md file cannot be parsed."""


@dataclass
class ParsedRobotMd:
    frontmatter: dict[str, Any]
    body: str
    source_path: Path | None = None


def parse_file(path: Path | str) -> ParsedRobotMd:
    """Parse a ROBOT.md file from disk."""
    p = Path(path)
    if not p.exists():
        raise ParseError(f"file not found: {p}")
    try:
        text = p.read_text()
    except OSError as e:
        raise ParseError(f"cannot read {p}: {e}") from e
    parsed = parse_text(text)
    return ParsedRobotMd(
        frontmatter=parsed.frontmatter,
        body=parsed.body,
        source_path=p,
    )


def parse_text(text: str) -> ParsedRobotMd:
    """Parse ROBOT.md content from a string."""
    if not text.lstrip().startswith("---"):
        raise ParseError(
            "no frontmatter found — ROBOT.md must start with a YAML frontmatter "
            "block delimited by '---'."
        )
    try:
        post = frontmatter.loads(text)
    except yaml.YAMLError as e:
        raise ParseError(f"frontmatter YAML parse error: {e}") from e
    except Exception as e:
        raise ParseError(f"frontmatter parse error: {e}") from e

    if not post.metadata:
        raise ParseError("frontmatter is empty or not a YAML mapping")

    return ParsedRobotMd(
        frontmatter=dict(post.metadata),
        body=post.content,
        source_path=None,
    )
