"""SP-AN Task 8 (after-window): manifest stays bound after the 30 s
window passes; v1 doesn't ship an unbind tool."""

from __future__ import annotations


def test_skill_text_warns_that_manifest_stays_bound(harness) -> None:
    assert harness.has_rule(
        "manifest stays bound",
        "Manifest unbinding is out of scope",
        "help edit ROBOT.md by hand",
    )
