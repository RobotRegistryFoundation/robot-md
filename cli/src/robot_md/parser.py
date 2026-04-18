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

    fm = dict(post.metadata)
    _upgrade_legacy_camera(fm)
    return ParsedRobotMd(
        frontmatter=fm,
        body=post.content,
        source_path=None,
    )


def _upgrade_legacy_camera(fm: dict) -> None:
    """Move singular physics.solver.camera → physics.solver.cameras[0] in place.

    The first driver whose protocol looks camera-ish (`depthai`, `realsense`,
    `v4l2`, `zed`, `uvc`) is used as driver_id. If no such driver exists,
    only upgrade if a driver with id 'camera' exists. Otherwise, leave the
    legacy camera in place and skip the upgrade.
    """
    solver = fm.get("physics", {}).get("solver", {})
    legacy = solver.get("camera")
    if not isinstance(legacy, dict):
        return
    drivers = fm.get("drivers") or []
    drivers_by_id = {d.get("id"): d for d in drivers if d.get("id")}

    camera_proto = {"depthai", "realsense", "v4l2", "zed", "uvc"}
    driver_id = next(
        (d["id"] for d in drivers if d.get("protocol") in camera_proto and d.get("id")),
        None,
    )

    # If no camera-protocol driver found, check if 'camera' driver exists
    if driver_id is None:
        if "camera" in drivers_by_id:
            driver_id = "camera"
        else:
            # Can't find a valid driver, skip upgrade
            return

    upgraded = {
        "driver_id": driver_id,
        "primary_stream": "rgb",
        "mount": legacy.get("mount", "world"),
        "extrinsic": legacy.get("extrinsic"),
    }
    solver["cameras"] = [upgraded]
    solver.pop("camera", None)
    fm.setdefault("_deprecations", []).append(
        "physics.solver.camera (singular) is deprecated; upgraded to cameras[]."
    )
