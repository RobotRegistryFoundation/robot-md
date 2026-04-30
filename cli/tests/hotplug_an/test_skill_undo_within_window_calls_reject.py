"""SP-AN Task 8 (within-window): operator-says-undo within 30 s pulls
through to a hotplug_confirm reject call."""

from __future__ import annotations


def test_skill_text_pulls_undo_through_to_hotplug_confirm_reject(harness) -> None:
    assert harness.has_rule(
        "operator says undo",
        'hotplug_confirm({event_id}, "reject")',
    )


def test_skill_text_mentions_30s_window(harness) -> None:
    assert harness.has_rule("within 30 s")
