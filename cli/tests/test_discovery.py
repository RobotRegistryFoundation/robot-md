"""Tests for robot-md discovery (.well-known/robot-md.json emit)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from robot_md.discovery import build_discovery, write_discovery

BOB_CONTENT = """---
rcan_version: "3.0"
metadata:
  robot_name: bob
  rrn: RRN-000000000042
  rcan_uri: rcan://rcan.dev/acme/so-arm101/1-0/bob-001
  manufacturer: acme
  model: so-arm101
  version: "1.0"
  device_id: bob-001
physics:
  type: arm
  dof: 6
drivers:
  - id: arm
    protocol: feetech
    port: /dev/ttyACM0
capabilities:
  - arm.pick
safety:
  estop:
    software: true
    response_ms: 100
---

# bob

## Identity
Bob is a test arm.

## What bob Can Do
Pick. That's it.

## Safety Gates
Software e-stop at 100ms.
"""


def _write_bob(tmp_path: Path) -> Path:
    p = tmp_path / "ROBOT.md"
    p.write_text(BOB_CONTENT)
    return p


def test_build_discovery_has_required_fields(tmp_path):
    m = _write_bob(tmp_path)
    doc = build_discovery(m, "https://bob.local/ROBOT.md")
    assert doc["robot_md_version"] == "1.1"
    assert doc["manifest_url"] == "https://bob.local/ROBOT.md"
    assert "sha256" in doc
    assert "last_modified" in doc


def test_build_discovery_rrn_derives_resolver(tmp_path):
    m = _write_bob(tmp_path)
    doc = build_discovery(m, "https://bob.local/ROBOT.md")
    assert doc["rrn"] == "RRN-000000000042"
    assert doc["public_resolver"] == "https://rcan.dev/r/RRN-000000000042"
    assert doc["rcan_uri"] == "rcan://rcan.dev/acme/so-arm101/1-0/bob-001"


def test_build_discovery_no_rrn_omits_resolver(tmp_path):
    # Manifest without an RRN should still produce a valid doc.
    content = BOB_CONTENT.replace("  rrn: RRN-000000000042\n", "")
    content = content.replace("  rcan_uri: rcan://rcan.dev/acme/so-arm101/1-0/bob-001\n", "")
    m = tmp_path / "ROBOT.md"
    m.write_text(content)
    doc = build_discovery(m, "https://bob.local/ROBOT.md")
    assert "rrn" not in doc
    assert "rcan_uri" not in doc
    assert "public_resolver" not in doc


def test_build_discovery_sha256_matches_bytes(tmp_path):
    m = _write_bob(tmp_path)
    expected = hashlib.sha256(m.read_bytes()).hexdigest()
    doc = build_discovery(m, "https://bob.local/ROBOT.md")
    assert doc["sha256"] == expected


def test_build_discovery_rejects_non_http_url(tmp_path):
    m = _write_bob(tmp_path)
    with pytest.raises(ValueError, match="manifest_url"):
        build_discovery(m, "bob.local/ROBOT.md")


def test_build_discovery_missing_manifest_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_discovery(tmp_path / "nope.ROBOT.md", "https://bob.local/ROBOT.md")


def test_write_discovery_creates_parent_dirs(tmp_path):
    m = _write_bob(tmp_path)
    out = tmp_path / "deep" / "nested" / "robot-md.json"
    doc = build_discovery(m, "https://bob.local/ROBOT.md")
    write_discovery(doc, out)
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded["manifest_url"] == "https://bob.local/ROBOT.md"


def test_write_discovery_is_deterministic(tmp_path):
    # Stable output (helpful for CI diffing): same doc → same bytes, and
    # top-level keys are sorted. (Nested dicts now exist under
    # `calibration_status`, so the flat-scan sort check has to look at the
    # top-level JSON object only.)
    m = _write_bob(tmp_path)
    doc = build_discovery(m, "https://bob.local/ROBOT.md")
    out_a = tmp_path / "robot-md-a.json"
    out_b = tmp_path / "robot-md-b.json"
    write_discovery(doc, out_a)
    write_discovery(doc, out_b)
    assert out_a.read_bytes() == out_b.read_bytes()
    loaded = json.loads(out_a.read_text())
    top_keys = list(loaded.keys())
    assert top_keys == sorted(top_keys)
