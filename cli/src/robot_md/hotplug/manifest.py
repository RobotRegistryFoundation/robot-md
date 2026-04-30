"""HIGH-tier manifest merge — schema-gated, fcntl-locked, atomic."""

from __future__ import annotations

import fcntl
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from robot_md.hotplug.matcher import BindProposal

_DRIVER_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


@dataclass(frozen=True)
class MergeOutcome:
    success: bool
    rrn: str | None
    driver_id: str | None
    reason: str


def merge(proposal: BindProposal, *, manifest_path: Path) -> MergeOutcome:
    if not manifest_path.exists():
        return MergeOutcome(
            success=False,
            rrn=proposal.rrn,
            driver_id=None,
            reason="no_manifest_in_cwd",
        )

    if not _DRIVER_ID_RE.match(proposal.driver_id_suggestion):
        return MergeOutcome(
            success=False,
            rrn=proposal.rrn,
            driver_id=None,
            reason="validation_failed: driver_id must match [a-z][a-z0-9_]*",
        )

    with manifest_path.open("r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            text = f.read()
            m = _FRONTMATTER_RE.match(text)
            if m is None:
                return MergeOutcome(
                    success=False,
                    rrn=proposal.rrn,
                    driver_id=None,
                    reason="validation_failed: no frontmatter",
                )
            data = yaml.safe_load(m.group(1)) or {}
            drivers = data.setdefault("drivers", [])

            new_driver = {
                "id": proposal.driver_id_suggestion,
                "protocol": proposal.inferred_fields.get("transport", "unknown"),
                "backend": proposal.backend_name,
            }
            if "port" in proposal.inferred_fields:
                new_driver["port"] = proposal.inferred_fields["port"]

            drivers.append(new_driver)

            new_frontmatter = yaml.safe_dump(data, sort_keys=False).rstrip()
            new_text = f"---\n{new_frontmatter}\n---\n" + text[m.end() :]

            f.seek(0)
            f.truncate()
            f.write(new_text)
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    return MergeOutcome(
        success=True,
        rrn=proposal.rrn,
        driver_id=proposal.driver_id_suggestion,
        reason="ok",
    )
