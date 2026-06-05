"""Tests for `robot-md commission` (A1) — the reality-check commissioning loop.

Classifier fixtures are REAL commission_probe telemetry captured live on Bob
(2026-06-05, hil_commission_probe_proof): the shoulder_pan clean reach and the
gripper close-discovery stall.
"""
from __future__ import annotations

from robot_md.commission import classify_probe

# --- real telemetry captured live on Bob ---
REACH = {  # shoulder_pan, in-range reach, zero stall
    "start_tick": 2429,
    "commanded_tick": 2493,
    "present_tick": 2477,
    "moved": True,
    "reached": True,
    "aborted_on_stall": False,
}
STALL = {  # gripper close-discovery: stalled at the empty-jaw floor
    "start_tick": 1697,
    "commanded_tick": 1401,
    "present_tick": 1455,
    "moved": True,
    "reached": False,
    "aborted_on_stall": True,
}
NO_MOVE = {  # commanded but the joint never advanced
    "start_tick": 2048,
    "commanded_tick": 2056,
    "present_tick": 2048,
    "moved": False,
    "reached": False,
    "aborted_on_stall": True,
}


def test_classify_reach_is_pass():
    cr = classify_probe("shoulder_pan", REACH)
    assert cr.status == "pass"
    assert cr.bucket == "commission"
    assert "shoulder_pan" in cr.name


def test_classify_stall_is_warn():
    cr = classify_probe("gripper", STALL)
    assert cr.status == "warn"
    assert cr.bucket == "commission"
    # the discovered endpoint tick must be surfaced for the operator
    assert "1455" in cr.detail


def test_classify_no_move_is_fail():
    cr = classify_probe("elbow_flex", NO_MOVE)
    assert cr.status == "fail"
    assert cr.bucket == "commission"


# --------------------------------------------------------------------------- targets
import math  # noqa: E402

import pytest  # noqa: E402
import yaml  # noqa: E402

from robot_md import commission  # noqa: E402

_TPR = 4096.0 / (2.0 * math.pi)

_FM = {
    "physics": {
        "kinematics": [
            {"id": "shoulder_pan", "servo_id": 1, "encoder_sign": 1, "zero_pose_steps": 1970},
            {"id": "gripper", "servo_id": 6, "encoder_sign": 1, "zero_pose_steps": 1539},
        ],
        "solver": {"gripper": {"open_steps": 1700, "close_steps": 1200}},
    }
}


def test_probe_targets_nongripper_from_shipped_rad_bounds():
    by = {p["joint_id"]: p for p in commission.probe_targets(_FM)}
    sp = by["shoulder_pan"]
    assert sp["motor_id"] == 1 and sp["is_gripper"] is False
    assert sp["target_max"] == round(1970 + 2.0 * _TPR)  # 3274
    assert sp["target_min"] == round(1970 - 2.0 * _TPR)  # 666


def test_probe_targets_gripper_uses_solver_ticks():
    by = {p["joint_id"]: p for p in commission.probe_targets(_FM)}
    g = by["gripper"]
    assert g["is_gripper"] is True
    assert g["target_min"] == 1200  # close_steps (direction -1)
    assert g["target_max"] == 1700  # open_steps (direction +1)


# ----------------------------------------------------------------- probe loop + restore
class _FakeGateway:
    """Records calls; returns canned commission_probe telemetry in order."""

    def __init__(self, probe_telemetry):
        self.calls = []
        self._it = iter(probe_telemetry)

    def __call__(self, actuator, tool, args, *, scope=None):
        self.calls.append((tool, dict(args), scope))
        if tool == "commission_probe":
            return {"telemetry": next(self._it)}
        if tool == "raw_tick_move":
            return {"telemetry": {"present_tick": args["ticks"], "commanded_tick": args["ticks"]}}
        raise AssertionError(f"unexpected tool {tool}")


def test_probe_joint_restores_to_start_after_each(monkeypatch):
    fake = _FakeGateway([REACH, REACH])
    monkeypatch.setattr(commission, "gateway_invoke", fake)
    plan = {"joint_id": "shoulder_pan", "motor_id": 1,
            "target_min": 666, "target_max": 3274, "is_gripper": False}
    res = commission.probe_joint(plan)
    tools = [c[0] for c in fake.calls]
    assert tools == ["commission_probe", "raw_tick_move", "commission_probe", "raw_tick_move"]
    restores = [c[1]["ticks"] for c in fake.calls if c[0] == "raw_tick_move"]
    assert restores == [REACH["start_tick"], REACH["start_tick"]]  # both to original 2429
    assert res["min_present"] == 2477 and res["max_present"] == 2477


def test_probe_joint_restores_on_exception(monkeypatch):
    state = {"n": 0, "calls": []}

    def boom(actuator, tool, args, *, scope=None):
        state["calls"].append((tool, dict(args)))
        if tool == "commission_probe":
            state["n"] += 1
            if state["n"] == 1:
                return {"telemetry": REACH}
            raise RuntimeError("probe 2 boom")
        return {"telemetry": {"present_tick": args["ticks"]}}

    monkeypatch.setattr(commission, "gateway_invoke", boom)
    plan = {"joint_id": "x", "motor_id": 1, "target_min": 1, "target_max": 2, "is_gripper": False}
    with pytest.raises(RuntimeError, match="boom"):
        commission.probe_joint(plan)
    # the finally restored to the start_tick captured from probe 1
    restores = [a["ticks"] for t, a in state["calls"] if t == "raw_tick_move"]
    assert REACH["start_tick"] in restores


# --------------------------------------------------------------------------- write-back
SAMPLE_MANIFEST = """---
metadata:
  rrn: RRN-000000000011
physics:
  kinematics:
    - id: shoulder_pan
      servo_id: 1
      encoder_sign: 1
      zero_pose_steps: 1970  # bob-calibrated anchor
    - id: gripper
      servo_id: 6
      encoder_sign: 1
      zero_pose_steps: 1539
  solver:
    gripper:
      open_steps: 1700
      close_steps: 1200
---

# Bob

Prose body that must survive verbatim.
"""


def _load_fm(path):
    text = path.read_text()
    end = text.find("\n---", 3)
    return yaml.safe_load(text[3:end])


def test_write_swaps_inverted_and_sets_commissioned_fields(tmp_path):
    p = tmp_path / "ROBOT.md"
    p.write_text(SAMPLE_MANIFEST)
    commission.write_commissioned_to_manifest(
        p, {"shoulder_pan": {"min_steps": 3274, "max_steps": 666}}, {}
    )
    fm = _load_fm(p)
    sp = {j["id"]: j for j in fm["physics"]["kinematics"]}["shoulder_pan"]
    assert sp["min_steps"] == 666 and sp["max_steps"] == 3274  # swapped to min<max
    assert sp["endpoint_source"] == "commissioned"
    assert "commissioned_at" in sp


def test_write_gripper_sets_floor_and_PRESERVES_close_steps(tmp_path):
    p = tmp_path / "ROBOT.md"
    p.write_text(SAMPLE_MANIFEST)
    # gripper kinematics entry endpoints + solver gripper (close_steps preserved at 1200)
    commission.write_commissioned_to_manifest(
        p,
        {"gripper": {"min_steps": 1455, "max_steps": 1697}},
        {"open_steps": 1697, "close_steps": 1200, "close_steps_empty": 1455},
    )
    fm = _load_fm(p)
    g = fm["physics"]["solver"]["gripper"]
    assert g["close_steps_empty"] == 1455      # the empty-jaw floor we measured
    assert g["close_steps"] == 1200            # PRESERVED grasp tick — the landmine
    assert g["open_steps"] == 1697
    gk = {j["id"]: j for j in fm["physics"]["kinematics"]}["gripper"]
    assert gk["min_steps"] == 1455 and gk["max_steps"] == 1697  # doctor-green for gripper


def test_write_preserves_comments_and_body(tmp_path):
    p = tmp_path / "ROBOT.md"
    p.write_text(SAMPLE_MANIFEST)
    commission.write_commissioned_to_manifest(
        p, {"shoulder_pan": {"min_steps": 666, "max_steps": 3274}}, {}
    )
    text = p.read_text()
    assert "bob-calibrated anchor" in text       # inline frontmatter comment preserved
    assert "Prose body that must survive verbatim." in text  # body verbatim


def test_endpoints_from_probes_gripper_mapping():
    probed = [{
        "joint_id": "gripper", "is_gripper": True,
        "min_present": 1455, "max_present": 1697, "checks": [],
    }]
    je, g = commission._endpoints_from_probes(probed, _FM)
    assert je["gripper"] == {"min_steps": 1455, "max_steps": 1697}
    assert g["close_steps_empty"] == 1455
    assert g["open_steps"] == 1697
    assert g["close_steps"] == 1200  # preserved from the manifest, not the probe


# ----------------------------------------------------------------- cli orchestration
class _Stub:
    def __init__(self, fm):
        self.frontmatter = fm


def test_cli_commission_self_test_never_writes(monkeypatch):
    monkeypatch.setattr("robot_md.parser.parse_file", lambda p: _Stub(_FM))
    monkeypatch.setattr(commission, "gateway_invoke", _FakeGateway([REACH, REACH, REACH, REACH]))
    monkeypatch.setattr(commission, "_write_evidence", lambda probed: None)
    calls = []
    monkeypatch.setattr(commission, "write_commissioned_to_manifest",
                        lambda *a, **k: calls.append("write") or 0)
    rc = commission.cli_commission("ROBOT.md", self_test=True)
    assert rc == 0
    assert "write" not in calls


def test_cli_commission_write_calls_write_resign_doctor_in_order(monkeypatch):
    import robot_md.doctor as doc
    import robot_md.provenance as prov

    monkeypatch.setattr("robot_md.parser.parse_file", lambda p: _Stub(_FM))
    monkeypatch.setattr(commission, "gateway_invoke", _FakeGateway([REACH, REACH, REACH, REACH]))
    monkeypatch.setattr(commission, "_write_evidence", lambda probed: None)
    order = []
    monkeypatch.setattr(commission, "write_commissioned_to_manifest",
                        lambda *a, **k: order.append("write") or 1)
    monkeypatch.setattr(prov, "resign_and_deploy",
                        lambda p, deploy=True: order.append("resign")
                        or {"kid": "bob-operator-2026", "deployed": True, "deploy_path": "/etc/x"})
    monkeypatch.setattr(doc, "run_all", lambda p: order.append("doctor") or [])
    monkeypatch.setattr(doc, "exit_code", lambda r, strict: 0)
    rc = commission.cli_commission("ROBOT.md", write=True)
    assert order == ["write", "resign", "doctor"]
    assert rc == 0


def test_commission_command_help():
    from typer.testing import CliRunner

    from robot_md.__main__ import app

    res = CliRunner().invoke(
        app, ["commission", "--help"], env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"}
    )
    assert res.exit_code == 0
    assert "--self-test" in res.stdout and "--write" in res.stdout
