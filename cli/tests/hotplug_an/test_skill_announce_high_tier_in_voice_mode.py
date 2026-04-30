"""SP-AN Task 7: skill-text contract for HIGH-tier announce + voice-mode
modality hierarchy."""

from __future__ import annotations


def test_skill_text_describes_high_tier_announce(harness) -> None:
    assert harness.has_rule(
        "HIGH-tier events that already resolved",
        "I bound it as the {driver_id} driver",
        "Say 'undo' to reject",
    )


def test_skill_text_announces_voice_first(harness) -> None:
    assert harness.has_rule(
        "voice mode",
        "announce by voice first",
        "mirror the same text to the chat",
    )
