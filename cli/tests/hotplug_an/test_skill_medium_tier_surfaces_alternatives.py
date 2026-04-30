"""SP-AN Task 9: MEDIUM/LOW-tier events surface alternatives + ask the
operator before binding."""

from __future__ import annotations


def test_skill_text_describes_medium_tier_alternatives(harness) -> None:
    assert harness.has_rule(
        "MEDIUM/LOW-tier pending events",
        "Surface the event with its alternatives",
        "pick a different option, or reject",
        "Call `hotplug_confirm` with their answer",
    )
