"""Named-pose helpers: teach by torque-off read-back, write to ROBOT.md.

Used by `robot-md pose teach` (CLI) and the `teach_poses` init phase.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

import yaml

from robot_md.parser import parse_file


def read_current_joints(bus: Any) -> dict[str, int]:
    """Snapshot every joint position via the servo bus."""
    return bus.read_positions()


def write_pose_to_manifest(
    manifest_path: Path,
    *,
    name: str,
    joints: dict[str, int],
    description: str | None = None,
) -> None:
    """Upsert physics.poses[name] in the manifest file.

    Preserves the prose body. Adds source=taught and today's ISO date.
    """
    parsed = parse_file(manifest_path)
    fm = dict(parsed.frontmatter)
    physics = dict(fm.get("physics") or {})
    poses = dict(physics.get("poses") or {})
    entry: dict[str, Any] = {
        "joints": dict(joints),
        "source": "taught",
        "taught_at": _dt.date.today().isoformat(),
    }
    if description:
        entry["description"] = description
    poses[name] = entry
    physics["poses"] = poses
    fm["physics"] = physics

    manifest_path.write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + parsed.body
    )


def teach_pose(
    bus: Any,
    manifest_path: Path,
    *,
    name: str,
    description: str | None = None,
) -> dict[str, int]:
    """Torque-off, read positions, torque back on, persist to manifest.

    Caller is responsible for operator prompts (TTY vs. non-interactive).
    Returns the joint dict that was written.
    """
    bus.torque(False)
    try:
        joints = read_current_joints(bus)
    finally:
        bus.torque(True)
    write_pose_to_manifest(manifest_path, name=name, joints=joints, description=description)
    return joints
