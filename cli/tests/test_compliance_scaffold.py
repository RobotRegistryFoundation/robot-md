"""Tests for the init compliance-scaffold phase."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from robot_md.init_phases.compliance_scaffold import (
    COMPLIANCE_README,
    DEMO_SCRIPT_TEMPLATE,
    phase_compliance_scaffold,
)


def test_phase_creates_scripts_and_compliance_dirs(tmp_path: Path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n# x\n")

    result = phase_compliance_scaffold(manifest)

    assert result.status == "ok"
    assert (tmp_path / "scripts" / "demo-eu-ai-act.sh").exists()
    assert (tmp_path / "compliance" / "README.md").exists()
    assert (tmp_path / "compliance" / ".gitkeep").exists()


def test_demo_script_is_executable(tmp_path: Path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n# x\n")

    phase_compliance_scaffold(manifest)

    demo = tmp_path / "scripts" / "demo-eu-ai-act.sh"
    mode = demo.stat().st_mode
    # owner / group / world execute bits all set (0o755)
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH


def test_phase_idempotent_does_not_overwrite_existing(tmp_path: Path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n# x\n")

    # First run creates the demo
    phase_compliance_scaffold(manifest)
    demo = tmp_path / "scripts" / "demo-eu-ai-act.sh"
    operator_custom = "#!/usr/bin/env bash\n# operator's custom version\n"
    demo.write_text(operator_custom)

    # Second run must not clobber operator changes
    result = phase_compliance_scaffold(manifest)
    assert demo.read_text() == operator_custom
    # status still ok, but the demo path is in 'skipped'
    assert "scripts/demo-eu-ai-act.sh" in (result.detail or {}).get("skipped", [])


def test_force_scripts_overwrites_existing(tmp_path: Path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n# x\n")
    phase_compliance_scaffold(manifest)

    demo = tmp_path / "scripts" / "demo-eu-ai-act.sh"
    demo.write_text("# stale\n")

    phase_compliance_scaffold(manifest, force_scripts=True)
    assert demo.read_text() == DEMO_SCRIPT_TEMPLATE


def test_demo_template_uses_relative_manifest_default(tmp_path: Path):
    """The default $MANIFEST in the demo must work when run from any cwd —
    it derives from the script's own location, not a hardcoded path."""
    assert "MANIFEST=" in DEMO_SCRIPT_TEMPLATE
    assert "$(dirname \"$0\")" in DEMO_SCRIPT_TEMPLATE


def test_compliance_readme_lists_each_artifact(tmp_path: Path):
    """README must mention each of the five RRF endpoints + Art-11 aggregator
    so an operator landing in compliance/ knows what each file is."""
    for schema in (
        "rcan-fria-v1",
        "rcan-ifu-v1",
        "rcan-safety-benchmark-v1",
        "rcan-incidents-v1",
        "robot-md-art11-summary-v0",
    ):
        assert schema in COMPLIANCE_README, f"README missing reference to {schema}"


def test_demo_template_has_no_bob_specific_paths(tmp_path: Path):
    """The template that ships in robot-md must not reference /home/craigm26/bob.
    That was the prototype path we developed against; production templates
    should be portable."""
    assert "/home/craigm26/bob" not in DEMO_SCRIPT_TEMPLATE
    assert "bob/scripts" not in DEMO_SCRIPT_TEMPLATE
