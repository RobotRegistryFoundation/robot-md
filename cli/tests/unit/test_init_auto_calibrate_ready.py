"""Init phase: auto-calibrate `ready` pose from DH params, no hardware."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from robot_md.init_phases.auto_calibrate_ready import phase_auto_calibrate_ready


def _write_manifest(tmp_path: Path, *, include_ready: bool = False, ik_provider: str | None = "inhouse-so-arm101") -> Path:
    fm = {
        "metadata": {"robot_name": "test-robot"},
        "physics": {
            "type": "arm", "dof": 6,
            "solver": {
                "convention": "DH",
                "base_frame": {"up": "z", "forward": "x"},
                "encoder": {"steps_per_rev": 4096},
                "gripper": {
                    "joint_id": "gripper",
                    "tip_offset_mm": [30, 0, 0],
                    "open_steps": 1700,
                    "close_steps": 1200,
                },
            },
            "kinematics": [
                {"id": "shoulder_pan", "axis": "z", "a_mm": 0, "d_mm": 60, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "shoulder_lift", "axis": "y", "a_mm": 125, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "elbow_flex", "axis": "y", "a_mm": 125, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_flex", "axis": "y", "a_mm": 60, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_roll", "axis": "x", "a_mm": 30, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "gripper", "axis": "y", "a_mm": 0, "d_mm": 0, "zero_pose_steps": 1200, "encoder_sign": 1},
            ],
        },
        "drivers": [{"id": "servos", "protocol": "feetech", "port": "/dev/null"}],
        "capabilities": ["arm.home"],
        "safety": {"estop": {"software": True}},
    }
    if ik_provider is not None:
        fm["physics"]["solver"]["ik_provider"] = ik_provider
    if include_ready:
        fm["physics"]["poses"] = {"ready": {"joints": {"shoulder_pan": 100, "shoulder_lift": 200, "elbow_flex": 300, "wrist_flex": 400, "wrist_roll": 500, "gripper": 1700}, "source": "taught"}}
    path = tmp_path / "ROBOT.md"
    path.write_text("---\n" + yaml.safe_dump(fm) + "---\n\n# test-robot\n\nbody\n")
    return path


def test_phase_auto_calibrate_writes_ready_pose(tmp_path):
    p = _write_manifest(tmp_path)
    result = phase_auto_calibrate_ready(manifest_path=p)
    assert result.status == "ok"

    fm = yaml.safe_load(p.read_text().split("---")[1])
    poses = fm["physics"].get("poses") or {}
    ready = poses.get("ready")
    assert ready is not None
    assert "joints" in ready
    required = {"shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"}
    assert required.issubset(ready["joints"].keys())
    assert ready.get("source") == "solved_from_dh"


def test_phase_auto_calibrate_is_idempotent_when_ready_already_taught(tmp_path):
    p = _write_manifest(tmp_path, include_ready=True)
    original = p.read_text()
    result = phase_auto_calibrate_ready(manifest_path=p)
    assert result.status == "skipped"
    assert result.detail.get("reason") == "already_set"
    assert p.read_text() == original


def test_phase_auto_calibrate_skips_when_no_ik_provider(tmp_path):
    p = _write_manifest(tmp_path, ik_provider=None)
    result = phase_auto_calibrate_ready(manifest_path=p)
    assert result.status == "skipped"
    assert result.detail.get("reason") == "no_ik_provider"


def _patch_other_phases(monkeypatch, init_module):
    """Patch every phase except `phase_auto_calibrate_ready`.

    `phase_write_manifest` must return status="ok" or default_flow aborts
    early (see init.py: `if r_write.status != "ok": return 2`), which would
    prevent the auto-calibrate phase from ever running.
    """
    from robot_md.init_phases import PhaseResult

    def ok_factory(phase_label):
        def _fn(*a, **kw):
            return PhaseResult(phase=phase_label, status="ok", message="", detail={})
        return _fn

    def skip_factory(phase_label):
        def _fn(*a, **kw):
            return PhaseResult(phase=phase_label, status="skipped", message="", detail={})
        return _fn

    monkeypatch.setattr(init_module, "phase_write_manifest", ok_factory("write_manifest"), raising=False)
    for name in ("phase_calibrate_sign", "phase_calibrate_zero", "phase_teach_poses"):
        monkeypatch.setattr(init_module, name, skip_factory(name.replace("phase_", "")), raising=False)


def test_default_flow_runs_auto_calibrate_phase(tmp_path, monkeypatch):
    """init.default_flow invokes the new phase by default."""
    from robot_md import init
    from robot_md.init_phases import PhaseResult

    calls = {"count": 0}

    def fake_phase(*, manifest_path):
        calls["count"] += 1
        return PhaseResult(phase="auto_calibrate_ready", status="ok", message="", detail={})

    monkeypatch.setattr(init, "phase_auto_calibrate_ready", fake_phase, raising=False)
    _patch_other_phases(monkeypatch, init)

    out = tmp_path / "ROBOT.md"
    out.write_text("---\nmetadata:\n  robot_name: r\n---\n\n# r\n\n")
    init.default_flow(
        out, robot_name="r", preset_name="so-arm101",
        do_install_mcp=False, do_install_skill=False,
        do_register=False, do_refresh_claude_md=False,
    )
    assert calls["count"] == 1


def test_default_flow_skips_auto_calibrate_when_flag_off(tmp_path, monkeypatch):
    from robot_md import init
    from robot_md.init_phases import PhaseResult

    calls = {"count": 0}

    def fake_phase(*, manifest_path):
        calls["count"] += 1
        return PhaseResult(phase="auto_calibrate_ready", status="ok", message="", detail={})

    monkeypatch.setattr(init, "phase_auto_calibrate_ready", fake_phase, raising=False)
    _patch_other_phases(monkeypatch, init)

    out = tmp_path / "ROBOT.md"
    out.write_text("---\nmetadata:\n  robot_name: r\n---\n\n# r\n\n")
    init.default_flow(
        out, robot_name="r", preset_name="so-arm101",
        do_install_mcp=False, do_install_skill=False,
        do_register=False, do_refresh_claude_md=False,
        do_auto_calibrate=False,
    )
    assert calls["count"] == 0
