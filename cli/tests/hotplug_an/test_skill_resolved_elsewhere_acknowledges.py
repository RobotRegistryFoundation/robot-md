"""SP-AN Task 10: when hotplug_confirm returns already_resolved (a CLI
or pendant ack came in first), Claude acknowledges instead of looping."""

from __future__ import annotations


def test_skill_text_handles_already_resolved(harness) -> None:
    assert harness.has_rule(
        "already_resolved",
        "operator confirmed it via another path",
        "happened from the terminal",
    )
