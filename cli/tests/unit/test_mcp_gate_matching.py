"""robot-md's MCP server refuses gated motion in the vocabulary its presets use.

The so_arm101 preset and examples/bob.ROBOT.md gate `destructive` and
`system`. robot-md-gateway reads those as MANIPULATE and EXECUTE/ACTUATE, and
for a tool that moves, a gate on any motion scope covers every motion. The
MCP server's matcher used to compare a gate's scope only with the
capability's family (`arm`), so under the preset's gates `arm.home` was sent
and ran. Now a gate that needs a person covers every motion, whatever scope
it names, except `commission`, which the gateway maps to no motion scope.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from robot_md import motion_gates
from robot_md.mcp.tools.execute_capability import execute_capability_tool
from tests.unit.test_mcp_motion_through_gateway import _ctx, _untouched

PRESETS = Path(__file__).resolve().parents[2] / "src" / "robot_md" / "presets"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _preset_gates(name: str) -> list[dict]:
    data = yaml.safe_load((PRESETS / f"{name}.yaml").read_text())
    return data["safety"]["hitl_gates"]


def _bob_gates() -> list[dict]:
    text = (REPO_ROOT / "examples" / "bob.ROBOT.md").read_text()
    front = text.split("---", 2)[1]
    return yaml.safe_load(front)["safety"]["hitl_gates"]


# --------------------------------------------------------------------------
# The reference manifests' own gates
# --------------------------------------------------------------------------


@pytest.mark.parametrize("gates", [_preset_gates("so_arm101"), _bob_gates()], ids=["preset", "bob"])
@pytest.mark.parametrize("capability", ["arm.home", "arm.pick", "arm.move_to"])
def test_the_reference_gates_refuse_every_motion(fixtures_dir, gateway_env, gates, capability):
    assert {g["scope"] for g in gates} >= {"destructive", "system"}
    ctx = _ctx(fixtures_dir, extra_caps=("arm.home", "arm.move_to"), gates=gates)
    r = execute_capability_tool(ctx, capability=capability, args={}, dry_run=False)
    assert r["status"] == "blocked", r
    assert r["error"]["reason"] == "hitl_gate"
    assert r["error"]["scope"] in {"destructive", "system"}
    assert "chat" in r["error"]["message"]
    assert gateway_env.requests == [], "a gated motion reached the gateway"
    _untouched(ctx)


def test_the_reference_gates_let_reads_through(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir, extra_caps=("status.report",), gates=_preset_gates("so_arm101"))
    r = execute_capability_tool(ctx, capability="status.report", args={}, dry_run=False)
    assert r["status"] == "ok"
    assert gateway_env.bodies[0]["scope"] == "OBSERVE"


def test_a_dry_run_of_a_gated_motion_is_refused_too(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir, gates=_preset_gates("so_arm101"))
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=True)
    assert r["error"]["reason"] == "hitl_gate"


def test_every_shipped_preset_with_gates_refuses_motion():
    """Every preset that declares a gate declares one that needs a person and
    covers motion (`destructive`, or on microduck `move` and `skill`), so
    robot-md's MCP server refuses all motion on each of them until an
    out-of-band confirmation exists."""
    for path in sorted(PRESETS.glob("*.yaml")):
        data = yaml.safe_load(path.read_text()) or {}
        gates = (data.get("safety") or {}).get("hitl_gates") or []
        if not gates:
            continue
        assert motion_gates.gates_covering_motion(gates), f"{path.name}: {gates} cover no motion"


# --------------------------------------------------------------------------
# The gateway's reading, mirrored
# --------------------------------------------------------------------------


def test_the_mirrored_vocabulary_matches_the_installed_gateway():
    gates_mod = pytest.importorskip("robot_md_gateway.cert.gates")
    policy_mod = pytest.importorskip("robot_md_gateway.cert.policy")
    if not hasattr(gates_mod, "_MANIFEST_GATE_SCOPE_MAP"):
        pytest.skip("this robot-md-gateway has no manifest gate mapping")
    assert dict(gates_mod._MANIFEST_GATE_SCOPE_MAP) == motion_gates.MANIFEST_GATE_SCOPES
    assert frozenset(policy_mod.MOTION_SCOPES) == motion_gates.MOTION_SCOPES


@pytest.mark.parametrize("scope", ["destructive", "system", "commission"])
@pytest.mark.parametrize("label", ["MANIPULATE", "NAVIGATE", "ACTUATE", "EXECUTE"])
def test_coverage_agrees_with_the_gateways_hitl_policy(scope, label):
    gates_mod = pytest.importorskip("robot_md_gateway.cert.gates")
    policy_cls = gates_mod.HiTLPolicy
    if not hasattr(policy_cls, "from_manifest_gates"):
        pytest.skip("this robot-md-gateway has no HiTLPolicy.from_manifest_gates")
    gate = {"scope": scope, "require_auth": True}
    policy = policy_cls.from_manifest_gates([gate])
    try:
        gateway_says = policy.requires(label, motion=True)
    except TypeError:
        pytest.skip("this robot-md-gateway's requires() has no motion flag")
    assert gateway_says == (motion_gates.coverage(gate) == "all_motion")


# --------------------------------------------------------------------------
# Any gate that needs a person covers every motion
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scope", ["arm", "arm.pick", "nav", "gripper"])
def test_a_gate_named_after_a_capability_or_family_covers_every_motion(
    fixtures_dir, gateway_env, scope
):
    """The capability name is caller-chosen, like the scope label: a gate on
    `arm` that `nav.goto` (or `arm.move_to` past a gate on `arm.pick`) could
    walk past is not a gate."""
    ctx = _ctx(
        fixtures_dir,
        extra_caps=("nav.goto", "gripper.close"),
        gates=[{"scope": scope, "require_auth": True}],
    )
    for capability in ("arm.pick", "arm.place", "nav.goto", "gripper.close"):
        r = execute_capability_tool(ctx, capability=capability, args={}, dry_run=False)
        assert r["error"]["reason"] == "hitl_gate", (capability, r)
    assert gateway_env.requests == []


def test_reads_pass_any_gate(fixtures_dir, gateway_env):
    ctx = _ctx(
        fixtures_dir,
        extra_caps=("status.report",),
        gates=[{"scope": "arm", "require_auth": True}],
    )
    r = execute_capability_tool(ctx, capability="status.report", args={}, dry_run=False)
    assert r["status"] == "ok"


@pytest.mark.parametrize("scope", ["mobile_base", "nav-high-speed", "manipulation", "Bogus"])
def test_a_scope_neither_layer_understands_refuses_every_motion(fixtures_dir, gateway_env, scope):
    ctx = _ctx(fixtures_dir, gates=[{"scope": scope, "require_auth": True}])
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["error"]["reason"] == "hitl_gate"
    assert gateway_env.requests == []


def test_a_commission_gate_does_not_cover_motion(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir, gates=[{"scope": "commission", "require_auth": True}])
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "ok"


def test_require_auth_false_covers_nothing(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir, gates=[{"scope": "destructive", "require_auth": False}])
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["status"] == "ok"


def test_a_gate_without_require_auth_counts_as_needing_a_person(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir, gates=[{"scope": "destructive"}])
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert r["error"]["reason"] == "hitl_gate"


def test_gate_scopes_match_in_any_case():
    assert motion_gates.coverage({"scope": "Destructive", "require_auth": True}) == "all_motion"


# --------------------------------------------------------------------------
# Scope labels
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("capability", "scope"),
    [
        ("arm.pick", "MANIPULATE"),
        ("gripper.close", "MANIPULATE"),
        ("nav.goto", "NAVIGATE"),
        ("head.turn", "ACTUATE"),
    ],
)
def test_motion_scope_labels(fixtures_dir, gateway_env, capability, scope):
    assert motion_gates.motion_scope_for(capability) == scope
    ctx = _ctx(fixtures_dir, extra_caps=(capability,) if capability != "arm.pick" else ())
    r = execute_capability_tool(ctx, capability=capability, args={}, dry_run=False)
    assert r["status"] == "ok", r
    assert gateway_env.bodies[-1]["scope"] == scope
