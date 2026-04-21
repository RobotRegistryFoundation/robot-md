"""Discovery payload includes calibration_status + learned_skills_summary."""

from __future__ import annotations

from robot_md.discovery import build_discovery
from robot_md.parser import parse_text


def _manifest_text() -> str:
    return """---
rcan_version: '3.0'
metadata: {robot_name: bob, rrn: RRN-000000000042}
physics:
  type: arm
  dof: 6
  kinematics:
    - id: shoulder_pan
      zero_pose_steps: 2048
  poses:
    ready:
      joints: {shoulder_pan: 1950}
      source: taught
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
learned_skills:
  - {id: red_lego_pick.2026-04-19, status: blocked}
  - {id: home.2026-04-19, status: ok}
---
# bob
"""


def test_discovery_includes_calibration_status():
    out = build_discovery(parse_text(_manifest_text()), manifest_url="https://x/ROBOT.md")
    cs = out["calibration_status"]
    assert cs["poses_ready"] == "ok"
    assert cs["hand_eye"] == "missing"
    assert cs["zero"] == "ok"


def test_discovery_includes_learned_skills_summary():
    out = build_discovery(parse_text(_manifest_text()), manifest_url="https://x/ROBOT.md")
    ls = out["learned_skills_summary"]
    assert "red_lego_pick.2026-04-19.blocked" in ls
    assert "home.2026-04-19.ok" in ls


def test_discovery_learned_skills_summary_empty_list_when_none():
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    out = build_discovery(parse_text(text), manifest_url="https://x/ROBOT.md")
    assert out["learned_skills_summary"] == []


def test_discovery_calibration_status_zero_missing_when_no_kinematics():
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    out = build_discovery(parse_text(text), manifest_url="https://x/ROBOT.md")
    assert out["calibration_status"]["zero"] == "missing"
    assert out["calibration_status"]["poses_ready"] == "missing"


def test_discovery_preserves_existing_fields():
    """Existing fields (rrn, manifest_url, etc.) must still be emitted."""
    out = build_discovery(parse_text(_manifest_text()), manifest_url="https://x/ROBOT.md")
    # Don't overspecify which fields exist — just check the payload is dict-like
    # and manifest_url is still round-tripped.
    assert isinstance(out, dict)
    assert out.get("manifest_url") == "https://x/ROBOT.md"
