"""robot-md publish-discovery — emit a .well-known/robot-md.json document.

The discovery document lets MCP clients, crawlers, and federated registries
locate a robot's ROBOT.md without prior configuration. Spec: §6.1 of
`spec/robot-md-v1.md`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from robot_md.parser import ParsedRobotMd, parse_file


def build_discovery(
    manifest: Path | ParsedRobotMd,
    manifest_url: str,
    *,
    content_type: str = "text/markdown; charset=utf-8",
    last_modified: str | None = None,
) -> dict[str, Any]:
    """Return a discovery-document dict for a ROBOT.md.

    `manifest` may be either a filesystem `Path` to a ROBOT.md (the classic
    CLI path — populates `sha256`/`last_modified` from the file on disk), or
    a pre-parsed `ParsedRobotMd` (used by tests and in-memory callers; the
    file-derived fields are simply omitted in that branch).

    `manifest_url` is the absolute URL at which the manifest will be served.
    `last_modified` defaults to the file's mtime in ISO-8601 Z-UTC (Path branch
    only; ignored for ParsedRobotMd input).

    Raises `FileNotFoundError` if a Path manifest is missing, `ValueError` if
    `manifest_url` is not a full `http(s)://` URL.
    """
    if not (manifest_url.startswith("http://") or manifest_url.startswith("https://")):
        raise ValueError(f"manifest_url must be http(s)://..., got {manifest_url!r}")

    if isinstance(manifest, ParsedRobotMd):
        parsed = manifest
        doc: dict[str, Any] = {
            "robot_md_version": "1.1",
            "manifest_url": manifest_url,
            "content_type": content_type,
        }
    else:
        manifest_path = manifest
        if not manifest_path.exists():
            raise FileNotFoundError(f"{manifest_path} does not exist")

        raw = manifest_path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()

        parsed = parse_file(manifest_path)

        if last_modified is None:
            ts = datetime.fromtimestamp(manifest_path.stat().st_mtime, tz=timezone.utc)
            last_modified = ts.strftime("%Y-%m-%dT%H:%M:%SZ")

        doc = {
            "robot_md_version": "1.1",
            "manifest_url": manifest_url,
            "content_type": content_type,
            "last_modified": last_modified,
            "sha256": sha256,
        }

    fm = parsed.frontmatter or {}
    md = fm.get("metadata") or {}

    rcan_version = fm.get("rcan_version")
    if rcan_version is not None:
        doc["rcan_version"] = str(rcan_version)
    if md.get("rrn"):
        doc["rrn"] = md["rrn"]
    if md.get("rcan_uri"):
        doc["rcan_uri"] = md["rcan_uri"]
    if md.get("rrn"):
        # Derive the public resolver unconditionally from the RRN. Operators
        # who host on a non-rcan.dev registry can override by passing a
        # public_resolver in the manifest (future: metadata.public_resolver).
        doc["public_resolver"] = f"https://rcan.dev/r/{md['rrn']}"

    # Calibration + learned-skill summary — so Mobile clients (no MCP) can
    # answer questions like "is bob ready to pick?" from the .well-known doc
    # alone. Reuses the MCP calibration_status resource so both surfaces stay
    # in lockstep (same ok/missing semantics for zero / hand_eye / poses_ready).
    from robot_md.mcp.resources import calibration_status as _calibration_status
    from robot_md.robot_spec import RobotSpec

    spec = RobotSpec.from_parsed(parsed)
    doc["calibration_status"] = _calibration_status(SimpleNamespace(spec=spec))
    doc["learned_skills_summary"] = [f"{s.id}.{s.status}" for s in spec.learned_skills]

    return doc


def write_discovery(doc: dict[str, Any], out_path: Path) -> None:
    """Write a discovery doc to `out_path`, creating parent dirs if needed."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
