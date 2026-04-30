from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.manifest import merge
from robot_md.hotplug.matcher import BindProposal


def test_merge_with_no_manifest_returns_clear_error(tmp_path: Path) -> None:
    manifest = tmp_path / "MISSING.md"  # does not exist
    outcome = merge(
        BindProposal(
            rrn=None,
            driver_id_suggestion="arm_servos",
            backend_name="lerobot",
            preset_name="so_arm101",
            capability_preview=[],
            inferred_fields={},
        ),
        manifest_path=manifest,
    )
    assert outcome.success is False
    assert outcome.reason == "no_manifest_in_cwd"
