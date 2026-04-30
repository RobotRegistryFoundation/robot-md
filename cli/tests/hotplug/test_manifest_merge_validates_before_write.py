from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.manifest import merge
from robot_md.hotplug.matcher import BindProposal


def test_invalid_proposal_does_not_write(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("""---
id: RRN-test
metadata:
  manufacturer: Test
  author: a@b
drivers: []
---
""")
    bad = BindProposal(
        rrn="RRN-test",
        driver_id_suggestion="bad name with spaces",  # invalid driver_id
        backend_name="lerobot",
        preset_name="so_arm101",
        capability_preview=[],
        inferred_fields={},
    )
    outcome = merge(bad, manifest_path=manifest)
    assert outcome.success is False
    assert "validation" in outcome.reason.lower()
    # Original manifest unchanged.
    assert "bad name with spaces" not in manifest.read_text()
