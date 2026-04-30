from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.manifest import MergeOutcome, merge
from robot_md.hotplug.matcher import BindProposal


def test_merge_appends_driver_preserves_others(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("""---
id: RRN-test
metadata:
  manufacturer: Test
  author: a@b
drivers:
  - id: existing
    protocol: realsense
    backend: realsense
---
""")
    proposal = BindProposal(
        rrn="RRN-test",
        driver_id_suggestion="arm_servos",
        backend_name="lerobot",
        preset_name="so_arm101",
        capability_preview=[],
        inferred_fields={"port": "/dev/ttyACM0", "transport": "feetech"},
    )
    outcome = merge(proposal, manifest_path=manifest)
    assert isinstance(outcome, MergeOutcome)
    assert outcome.success is True
    text = manifest.read_text()
    assert "id: existing" in text  # preserved
    assert "id: arm_servos" in text  # appended
    assert "backend: lerobot" in text
