"""Tests that the bundled SKILL.md ships the expected guidance sections."""

from __future__ import annotations

from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[1] / "src" / "robot_md" / "skills" / "using-robot-md.SKILL.md"
)


def test_skill_contains_search_before_write_section():
    src = SKILL.read_text()
    assert "Before writing an actuator from scratch" in src
    assert "robot-md actuator search" in src
    assert "robot-md actuator publish" in src


# --- motion rules (robot-md-gateway is the only path) -----------------------
#
# The skill used to tell Claude to move the arm after a "yes" in chat, and to
# pass that along as a confirmation. These pin the replacement. The same
# assertions run against the canonical copy in robot-md-mcp.


def test_skill_never_treats_a_chat_yes_as_authorization():
    src = SKILL.read_text()
    assert 'A chat "yes" is never authorization for motion' in src
    lowered = src.lower()
    for phrase in (
        "yes, authorize this specific action",
        "authorize this specific action",
        "pause and ask the operator to authorize",
        "confirm_token=",
    ):
        assert phrase not in lowered, f"skill still says {phrase!r}"


def test_skill_routes_motion_only_through_the_gateway():
    src = SKILL.read_text()
    assert "Motion goes only through robot-md-gateway" in src
    assert "never run a command or script that opens it" in src
    # The old upgrade path to motion was the hardware extra plus a reconnect.
    assert "pip install 'robot-md[hardware]'" not in src
    # A tool that never existed.
    assert "mcp__robot-md__invoke` with" not in src


def test_skill_requires_a_person_at_the_machine_with_a_hardware_stop():
    src = SKILL.read_text()
    assert "A person at the machine, with a hardware stop, comes before any motion" in src
    assert "The `estop` tool is a software stop, not that hardware stop" in src


def test_skill_leaves_test_runs_and_clearing_stops_to_the_person():
    src = SKILL.read_text()
    assert "Test runs are started by the person, never by you" in src
    assert "Never call `estop_clear` to resume on your own" in src


def test_skill_states_how_it_relates_to_bounded_embodiment():
    """bounded-embodiment's rule on claude-code-plugins main: no motion on real
    hardware by any route. The skill describes that rule as it stands, and
    keeps "follow the stricter rule"."""
    src = SKILL.read_text()
    assert "### How this skill relates to the bounded-embodiment skill" in src
    assert "you never start motion on real hardware by any route" in src
    assert "follow the stricter rule" in src


# --- what robot-md's MCP server enforces (the skill must say the same) -------


def test_skill_says_a_motion_gate_refuses_every_motion():
    """robot_md.motion_gates: a gate that needs a person covers every motion,
    and the so-arm101 preset's gates (destructive, system) need one."""
    src = SKILL.read_text()
    assert "refuse every capability that moves (`hitl_gate`)" in src
    assert "on a manifest made from it every motion is refused for now" in src


def test_skill_says_ok_is_not_arrival():
    src = SKILL.read_text()
    assert "`status: ok` means the gateway ran the call, not that the arm arrived" in src
    assert "`reached`" in src


def test_skill_keeps_claude_off_the_servo_port():
    src = SKILL.read_text()
    assert "robot-md doctor --path ROBOT.md --hardware off" in src
    # robot-md init probes every serial port: the person runs it.
    assert "Give the person `robot-md init" in src
    assert "robot-md pose teach" in src


def test_skill_says_clearing_after_a_trip_takes_both_clears_and_a_restart():
    src = SKILL.read_text()
    assert "the gateway needs its own clear as well as the arm's" in src
    assert "the person restarts this MCP server" in src
