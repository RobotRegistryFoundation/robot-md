"""phase_teach_poses skips on non-interactive, teaches 'ready' on TTY."""

from __future__ import annotations

from unittest.mock import patch

from robot_md.init_phases import PhaseResult


def test_phase_skips_when_non_interactive(tmp_path):
    from robot_md.init_phases.teach_poses import phase_teach_poses

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nrcan_version: '3.0'\n---\n# x\n")
    r: PhaseResult = phase_teach_poses(manifest_path=manifest, interactive=False)
    assert r.status == "skipped"
    assert "non-interactive" in r.message.lower()


def test_phase_teaches_ready_when_interactive(tmp_path):
    from robot_md.init_phases.teach_poses import phase_teach_poses

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech}]\n"
        "capabilities: [status.report]\n"
        "safety: {estop: {software: true, response_ms: 100}}\n"
        "---\n# bob\n"
    )

    class _Bus:
        def torque(self, on):
            pass

        def read_positions(self):
            return {"shoulder_pan": 2048, "shoulder_lift": 1600}

    with (
        patch("robot_md.init_phases.teach_poses._open_feetech_bus", return_value=_Bus()),
        patch("robot_md.init_phases.teach_poses._prompt_confirm", return_value=True),
    ):
        r = phase_teach_poses(manifest_path=manifest, interactive=True)
    assert r.status == "ok", r
    assert "ready" in r.detail.get("pose_names", [])
