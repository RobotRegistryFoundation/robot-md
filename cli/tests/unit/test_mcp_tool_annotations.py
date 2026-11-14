"""Every MCP tool states its annotations, and the read-only set is pinned.

Conservative MCP clients (duck-studio's, for one) treat a tool with no
annotations as destructive and open-world, so they can call none of ours
freely. A new tool must make an explicit choice: test_every_tool_states_all_hints
fails for a tool registered with a bare `@server.tool()`, and
test_read_only_table_matches fails until the tool is added to EXPECTED.
"""

from __future__ import annotations

import pytest

from robot_md.mcp.context import load_context
from robot_md.mcp.server import build_server

HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")

# name -> (readOnly, destructive, idempotent, openWorld)
# Decided from each implementation, not from its name. See the comment above
# each tool in robot_md/mcp/server.py for the reason.
EXPECTED: dict[str, tuple[bool, bool, bool, bool]] = {
    # read-only
    "render": (True, False, True, False),
    "validate": (True, False, True, False),
    "doctor_summary": (True, False, True, False),
    "vision_find": (True, False, True, True),
    "spatial_eval_dry_run": (True, False, True, False),
    "spatial_eval_kit": (True, False, True, False),
    "spatial_eval_replay": (True, False, True, False),
    "spatial_eval_verify": (True, False, True, True),
    # hotplug_review reads the queue file without opening an EventQueue, so
    # it neither creates the file nor appends an alert on malformed lines.
    "hotplug_review": (True, False, True, False),
    # motion and the gateway
    "estop": (False, False, True, True),
    "estop_clear": (False, True, True, True),
    "execute_capability": (False, True, False, True),
    "execute_task": (False, True, False, True),
    # local writes
    "record_skill": (False, True, True, False),
    "discover": (False, False, False, True),
    "spatial_eval_init": (False, False, True, False),
    "spatial_eval_run_probe": (False, False, False, True),
    "spatial_eval_run_execute": (False, True, False, True),
    "spatial_eval_run_full": (False, True, False, True),
    "spatial_eval_submit_to_rrf": (False, False, False, True),
    # hotplug_confirm checks for a prior resolution and an already-declared
    # driver before writing, so a repeated call leaves ROBOT.md byte-identical.
    "hotplug_confirm": (False, True, True, False),
}

READ_ONLY_TOOLS = {name for name, hints in EXPECTED.items() if hints[0]}


@pytest.fixture
async def tools(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    server = build_server(ctx)
    return {t.name: t for t in await server.list_tools()}


async def test_every_tool_states_all_hints(tools):
    assert tools, "server registered no tools"
    for name, tool in tools.items():
        ann = tool.annotations
        assert ann is not None, f"{name} has no annotations"
        unset = [h for h in HINTS if getattr(ann, h) is None]
        assert not unset, f"{name} leaves {unset} unset"
        assert tool.title, f"{name} has no title"
        assert ann.title == tool.title, f"{name}: annotations.title != title"


async def test_registered_tools_match_table(tools):
    assert set(tools) == set(EXPECTED), (
        f"unpinned tools: {sorted(set(tools) - set(EXPECTED))}; "
        f"pinned but gone: {sorted(set(EXPECTED) - set(tools))}"
    )


@pytest.mark.parametrize("name", sorted(EXPECTED))
async def test_hints_match_table(tools, name):
    ann = tools[name].annotations
    got = tuple(getattr(ann, h) for h in HINTS)
    assert got == EXPECTED[name], f"{name}: got {dict(zip(HINTS, got, strict=True))}"


def test_read_only_set_is_pinned():
    pinned = {
        "render",
        "validate",
        "doctor_summary",
        "vision_find",
        "spatial_eval_dry_run",
        "spatial_eval_kit",
        "spatial_eval_replay",
        "spatial_eval_verify",
        "hotplug_review",
    }
    assert pinned == READ_ONLY_TOOLS


async def test_motion_tools_are_never_read_only(tools):
    for name in ("estop", "estop_clear", "execute_capability", "execute_task"):
        ann = tools[name].annotations
        assert ann.readOnlyHint is False, name
        assert ann.openWorldHint is True, name


async def test_a_bare_tool_fails_the_check(fixtures_dir):
    """Prove the check can fail: a tool added without annotations is caught."""
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    server = build_server(ctx)

    @server.tool()
    def unannotated() -> str:
        return ""

    listed = {t.name: t for t in await server.list_tools()}
    assert listed["unannotated"].annotations is None
    assert set(listed) != set(EXPECTED)
