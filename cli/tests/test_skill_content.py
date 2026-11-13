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
    src = SKILL.read_text()
    assert "### How this skill relates to the bounded-embodiment skill" in src
    assert "They differ in one place, for a reason" in src
    assert "the stricter rule wins" in src
