"""Pure-function precondition evaluator — returns list[PreconditionFailure]."""
from __future__ import annotations

from types import SimpleNamespace

from robot_md.preconditions import PreconditionFailure, evaluate
from robot_md.robot_spec import CapabilityContract, Precondition


def _missing_spec():
    return SimpleNamespace(
        physics=SimpleNamespace(poses={}, cameras=(), solver={}, workspace=None),
        learned_skills=[],
    )


def _present_spec():
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
    ok, failed = evaluate(contract, _present_spec(), backend_resolved=True)
    assert ok
    assert failed == []


def test_pose_taught_missing_returns_structured_failure():
    contract = CapabilityContract(
        preconditions=(Precondition(kind="pose_taught", name="ready", detail={}),)
    )
    ok, failed = evaluate(contract, _missing_spec(), backend_resolved=True)
    assert not ok
    assert len(failed) == 1
    f = failed[0]
    assert isinstance(f, PreconditionFailure)
    assert f.kind == "pose_taught"
    assert f.name == "ready"
    assert "pose 'ready' not taught" in f.message
    assert f.suggested_fix == "robot-md pose teach ready"


def test_extrinsic_present_missing_has_calibrate_fix():
    contract = CapabilityContract(
        preconditions=(Precondition(kind="extrinsic_present", name=None, detail={}),)
    )
    ok, failed = evaluate(contract, _missing_spec(), backend_resolved=True)
    assert not ok
    assert failed[0].kind == "extrinsic_present"
    assert failed[0].suggested_fix == "robot-md calibrate --extrinsic"


def test_backend_resolved_false_has_driver_check_fix():
    contract = CapabilityContract(
        preconditions=(Precondition(kind="backend_resolved", name=None, detail={}),)
    )
    ok, failed = evaluate(contract, _present_spec(), backend_resolved=False)
    assert not ok
    assert failed[0].kind == "backend_resolved"
    assert failed[0].suggested_fix is not None
    assert "drivers" in failed[0].suggested_fix


def test_ik_provider_missing_has_manifest_fix():
    spec = SimpleNamespace(
        physics=SimpleNamespace(poses={}, cameras=(), solver={}, workspace=None),
        learned_skills=[],
    )
    contract = CapabilityContract(
        preconditions=(Precondition(kind="ik_provider_set", name=None, detail={}),)
    )
    ok, failed = evaluate(contract, spec, backend_resolved=True)
    assert not ok
    assert failed[0].kind == "ik_provider_set"
    assert failed[0].suggested_fix is not None
    assert "ik_provider" in failed[0].suggested_fix


def test_workspace_declared_missing_has_manifest_fix():
    spec = SimpleNamespace(
        physics=SimpleNamespace(poses={}, cameras=(), solver={}, workspace=None),
        learned_skills=[],
    )
    contract = CapabilityContract(
        preconditions=(Precondition(kind="workspace_declared", name=None, detail={}),)
    )
    ok, failed = evaluate(contract, spec, backend_resolved=True)
    assert not ok
    assert failed[0].kind == "workspace_declared"
    assert failed[0].suggested_fix is not None
    assert "workspace" in failed[0].suggested_fix


def test_learned_skill_missing_has_null_fix():
    """No single CLI command records a skill (skill recording is via the
    MCP record_skill tool, not a CLI verb). suggested_fix is None."""
    spec = SimpleNamespace(
        physics=SimpleNamespace(poses={}, cameras=(), solver={}, workspace=None),
        learned_skills=[],
    )
    contract = CapabilityContract(
        preconditions=(Precondition(kind="learned_skill_ok", name="red_lego_pick", detail={}),)
    )
    ok, failed = evaluate(contract, spec, backend_resolved=True)
    assert not ok
    assert failed[0].kind == "learned_skill_ok"
    assert failed[0].name == "red_lego_pick"
    assert "red_lego_pick" in failed[0].message
    assert failed[0].suggested_fix is None


def test_learned_skill_blocked_has_null_fix():
    spec = SimpleNamespace(
        physics=SimpleNamespace(poses={}, cameras=(), solver={}, workspace=None),
        learned_skills=[SimpleNamespace(id="red_lego_pick", status="blocked")],
    )
    contract = CapabilityContract(
        preconditions=(Precondition(kind="learned_skill_ok", name="red_lego_pick", detail={}),)
    )
    ok, failed = evaluate(contract, spec, backend_resolved=True)
    assert not ok
    assert "status=blocked" in failed[0].message
    assert failed[0].suggested_fix is None  # no single remediation command


def test_learned_skill_without_name_returns_structured_failure():
    """Precondition with kind=learned_skill_ok but name=None should emit
    a structured failure with None fix."""
    contract = CapabilityContract(
        preconditions=(Precondition(kind="learned_skill_ok", name=None, detail={}),)
    )
    ok, failed = evaluate(contract, _missing_spec(), backend_resolved=True)
    assert not ok
    assert failed[0].kind == "learned_skill_ok"
    assert failed[0].name is None
    assert "missing 'name'" in failed[0].message
    assert failed[0].suggested_fix is None


def test_unknown_kind_returns_unfixable_structured_failure():
    contract = CapabilityContract(
        preconditions=(Precondition(kind="cosmic_rays_ok", name=None, detail={}),)
    )
    ok, failed = evaluate(contract, _missing_spec(), backend_resolved=True)
    assert not ok
    assert failed[0].kind == "cosmic_rays_ok"
    assert failed[0].suggested_fix is None
    assert "unknown precondition kind" in failed[0].message


def test_multiple_preconditions_preserve_declared_order():
    contract = CapabilityContract(preconditions=(
        Precondition(kind="pose_taught", name="ready", detail={}),
        Precondition(kind="extrinsic_present", name=None, detail={}),
        Precondition(kind="backend_resolved", name=None, detail={}),
    ))
    ok, failed = evaluate(contract, _missing_spec(), backend_resolved=False)
    assert not ok
    assert len(failed) == 3
    assert [f.kind for f in failed] == [
        "pose_taught", "extrinsic_present", "backend_resolved"
    ]


def test_empty_contract_passes():
    contract = CapabilityContract(preconditions=())
    ok, failed = evaluate(contract, _missing_spec(), backend_resolved=True)
    assert ok
    assert failed == []
