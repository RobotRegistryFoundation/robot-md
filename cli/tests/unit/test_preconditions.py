"""Pure-function precondition evaluator."""
from __future__ import annotations

from types import SimpleNamespace

from robot_md.preconditions import evaluate
from robot_md.robot_spec import CapabilityContract, Precondition


def _pose_ready_missing_spec():
    return SimpleNamespace(
        physics=SimpleNamespace(
            poses={}, cameras=(), solver={}, workspace=None,
        ),
        learned_skills=[],
    )


def _pose_ready_present_spec():
    return SimpleNamespace(
        physics=SimpleNamespace(
            poses={"ready": SimpleNamespace(joints={"a": 1}, source="taught")},
            cameras=(SimpleNamespace(extrinsic=(1, 0, 0, 0)),),
            solver={"ik_provider": "inhouse-so-arm101"},
            workspace=SimpleNamespace(bounds_mm={"x": (-200, 200)}),
        ),
        learned_skills=[],
    )


def test_pose_taught_ok():
    contract = CapabilityContract(
        preconditions=(Precondition(kind="pose_taught", name="ready", detail={}),)
    )
    ok, failed = evaluate(contract, _pose_ready_present_spec(), backend_resolved=True)
    assert ok
    assert failed == []


def test_pose_taught_missing():
    contract = CapabilityContract(
        preconditions=(Precondition(kind="pose_taught", name="ready", detail={}),)
    )
    ok, failed = evaluate(contract, _pose_ready_missing_spec(), backend_resolved=True)
    assert not ok
    assert any("pose 'ready' not taught" in f for f in failed)


def test_extrinsic_present_missing():
    contract = CapabilityContract(
        preconditions=(Precondition(kind="extrinsic_present", name=None, detail={}),)
    )
    ok, failed = evaluate(contract, _pose_ready_missing_spec(), backend_resolved=True)
    assert not ok
    assert any("extrinsic" in f for f in failed)


def test_backend_resolved_false():
    contract = CapabilityContract(
        preconditions=(Precondition(kind="backend_resolved", name=None, detail={}),)
    )
    ok, _failed = evaluate(contract, _pose_ready_present_spec(), backend_resolved=False)
    assert not ok


def test_ik_provider_missing():
    spec = SimpleNamespace(
        physics=SimpleNamespace(poses={}, cameras=(), solver={}, workspace=None),
        learned_skills=[],
    )
    contract = CapabilityContract(
        preconditions=(Precondition(kind="ik_provider_set", name=None, detail={}),)
    )
    ok, failed = evaluate(contract, spec, backend_resolved=True)
    assert not ok
    assert any("ik_provider" in f for f in failed)


def test_workspace_declared_missing():
    spec = SimpleNamespace(
        physics=SimpleNamespace(poses={}, cameras=(), solver={}, workspace=None),
        learned_skills=[],
    )
    contract = CapabilityContract(
        preconditions=(Precondition(kind="workspace_declared", name=None, detail={}),)
    )
    ok, failed = evaluate(contract, spec, backend_resolved=True)
    assert not ok
    assert any("workspace" in f for f in failed)


def test_learned_skill_ok_missing():
    spec = SimpleNamespace(
        physics=SimpleNamespace(poses={}, cameras=(), solver={}, workspace=None),
        learned_skills=[],
    )
    contract = CapabilityContract(
        preconditions=(Precondition(kind="learned_skill_ok", name="red_lego_pick", detail={}),)
    )
    ok, failed = evaluate(contract, spec, backend_resolved=True)
    assert not ok
    assert any("red_lego_pick" in f for f in failed)


def test_learned_skill_blocked_status():
    spec = SimpleNamespace(
        physics=SimpleNamespace(poses={}, cameras=(), solver={}, workspace=None),
        learned_skills=[SimpleNamespace(id="red_lego_pick", status="blocked")],
    )
    contract = CapabilityContract(
        preconditions=(Precondition(kind="learned_skill_ok", name="red_lego_pick", detail={}),)
    )
    ok, failed = evaluate(contract, spec, backend_resolved=True)
    assert not ok
    assert any("status=blocked" in f for f in failed)


def test_multiple_preconditions_all_report():
    contract = CapabilityContract(preconditions=(
        Precondition(kind="pose_taught", name="ready", detail={}),
        Precondition(kind="extrinsic_present", name=None, detail={}),
        Precondition(kind="backend_resolved", name=None, detail={}),
    ))
    ok, failed = evaluate(contract, _pose_ready_missing_spec(), backend_resolved=False)
    assert not ok
    assert len(failed) == 3


def test_empty_contract_passes():
    contract = CapabilityContract(preconditions=())
    ok, failed = evaluate(contract, _pose_ready_missing_spec(), backend_resolved=True)
    assert ok
    assert failed == []
