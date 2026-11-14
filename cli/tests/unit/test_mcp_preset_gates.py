"""The so-arm101 preset's own gates refuse every motion it declares.

`robot-md init --preset so-arm101` writes `safety.hitl_gates` with
`destructive` and `system`, both `require_auth: true`. robot-md's MCP server
refuses every capability that moves while such a gate stands (`hitl_gate`):
the confirmation those gates need has to come from a person outside the
conversation, and robot-md has no path for one yet. Reads still work.

robot-md#114, as merged, matched a gate only against a capability's family
(`arm`), so under these gates every motion was sent to the gateway, and
`arm.home` ran. This test fails there.
"""

from __future__ import annotations

from robot_md.autodetect import Scan
from robot_md.init import load_presets, merge_preset_into_draft, render_draft
from robot_md.mcp.context import load_context
from robot_md.mcp.tools.execute_capability import READ_ONLY_CAPABILITIES, execute_capability_tool

PRESET = "so_arm101"


def _manifest_from_preset(tmp_path, name=PRESET):
    """The ROBOT.md `robot-md init --preset <name>` writes, with no hardware scan."""
    (preset,) = [p for p in load_presets() if p.name == name]
    frontmatter = merge_preset_into_draft(preset, "preset-bot", Scan())
    path = tmp_path / "ROBOT.md"
    path.write_text(render_draft(frontmatter, preset.data.get("body_hints") or {}))
    return path


def test_every_motion_the_so_arm101_preset_declares_is_refused(tmp_path, gateway_env):
    ctx = load_context(_manifest_from_preset(tmp_path))
    gates = {g["scope"]: g.get("require_auth") for g in ctx.spec.safety.hitl_gates}
    assert gates == {"destructive": True, "system": True}

    declared = sorted(ctx.spec.capabilities)
    reads = [c for c in declared if c in READ_ONLY_CAPABILITIES]
    motions = [c for c in declared if c not in READ_ONLY_CAPABILITIES]
    assert {"arm.home", "arm.pick", "arm.place", "arm.reach"} <= set(motions), declared
    assert "status.report" in reads, declared

    for capability in motions:
        r = execute_capability_tool(ctx, capability=capability, args={}, dry_run=False)
        assert r["status"] == "blocked", (capability, r)
        assert r["error"]["reason"] == "hitl_gate", (capability, r)
    assert gateway_env.requests == [], (
        "a motion under the preset's gates reached the gateway: "
        f"{[b.get('tool_name') for b in gateway_env.bodies]}"
    )

    for capability in reads:
        r = execute_capability_tool(ctx, capability=capability, args={}, dry_run=False)
        assert r["status"] == "ok", (capability, r)
    assert [b["tool_name"] for b in gateway_env.bodies] == reads
    assert {b["scope"] for b in gateway_env.bodies} == {"OBSERVE"}


def test_every_capability_but_the_read_is_refused_on_the_microduck_preset(tmp_path, gateway_env):
    """The microduck preset gates `move` and `skill` with require_auth: true and
    `sound` with require_auth: false. A gate that needs a person covers every
    capability that isn't a read, so `sound.play` is refused too: the `sound`
    gate covers nothing, and it exempts nothing from the other two.
    robot-md-gateway maps none of these scopes, so with
    ROBOT_MD_HITL_FROM_MANIFEST=1 it enforces none of them: this server's
    refusal is the only layer that keeps them."""
    ctx = load_context(_manifest_from_preset(tmp_path, "microduck"))
    gates = {g["scope"]: g.get("require_auth") for g in ctx.spec.safety.hitl_gates}
    assert gates == {"move": True, "skill": True, "sound": False}

    declared = sorted(ctx.spec.capabilities)
    reads = [c for c in declared if c in READ_ONLY_CAPABILITIES]
    others = [c for c in declared if c not in READ_ONLY_CAPABILITIES]
    assert reads == ["status.report"], declared
    assert {"move.walk", "move.turn", "skill.kick_left", "sound.play"} <= set(others), declared

    for capability in others:
        r = execute_capability_tool(ctx, capability=capability, args={}, dry_run=False)
        assert r["status"] == "blocked", (capability, r)
        assert r["error"]["reason"] == "hitl_gate", (capability, r)
    assert gateway_env.requests == []

    r = execute_capability_tool(ctx, capability="status.report", args={}, dry_run=False)
    assert r["status"] == "ok", r
    assert [(b["tool_name"], b["scope"]) for b in gateway_env.bodies] == [
        ("status.report", "OBSERVE")
    ]
