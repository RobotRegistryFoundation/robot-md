"""CLI surface tests for incidents subcommand group (P1.3).

The data layer is covered by tests/test_incidents.py. These cover the CLI
wiring of `robot-md incidents record / report / list` against a temp HOME.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("ruamel.yaml")

from robot_md.__main__ import app

runner = CliRunner()

BOB_MIN = """\
---
rcan_version: "3.0"
metadata:
  robot_name: bob
  manufacturer: Acme
  model: rx-1
  firmware_version: 1.0.0
  rrn: RRN-000000000099
physics: { type: arm, dof: 6 }
drivers:
  - { id: arm, protocol: feetech, port: /dev/null }
safety:
  estop: { software: true, hardware: false, response_ms: 100 }
capabilities: [navigate]
---
# bob
"""


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    p = tmp_path / "ROBOT.md"
    p.write_text(BOB_MIN)
    return p


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    """Isolate ~/.robot-md/incidents under a tmp HOME for the test."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_incidents_record_writes_jsonl_under_home(manifest, home):
    result = runner.invoke(
        app,
        [
            "incidents", "record", str(manifest),
            "--severity", "other",
            "--category", "test_event",
            "--description", "smoke test entry",
        ],
    )
    assert result.exit_code == 0, result.stdout
    log = home / ".robot-md" / "incidents" / "RRN-000000000099.jsonl"
    assert log.exists()
    entry = json.loads(log.read_text().strip())
    assert entry["category"] == "test_event"
    assert entry["severity"] == "other"


def test_incidents_record_rejects_unknown_severity(manifest, home):
    result = runner.invoke(
        app,
        [
            "incidents", "record", str(manifest),
            "--severity", "BOGUS",
            "--category", "x",
            "--description", "y",
        ],
    )
    assert result.exit_code != 0


def test_incidents_list_returns_recorded(manifest, home):
    runner.invoke(
        app,
        [
            "incidents", "record", str(manifest),
            "--severity", "life_health",
            "--category", "motor_stall",
            "--description", "wrist_flex stalled at +90°",
        ],
    )
    result = runner.invoke(app, ["incidents", "list", str(manifest)])
    assert result.exit_code == 0, result.stdout
    assert "motor_stall" in result.stdout
    assert "life_health" in result.stdout


def test_incidents_list_empty_log(manifest, home):
    result = runner.invoke(app, ["incidents", "list", str(manifest)])
    assert result.exit_code == 0, result.stdout
    assert "no incidents" in result.stdout.lower()


def test_incidents_report_returns_v1_shape(manifest, home):
    runner.invoke(
        app,
        [
            "incidents", "record", str(manifest),
            "--severity", "other",
            "--category", "x",
            "--description", "y",
        ],
    )
    result = runner.invoke(app, ["incidents", "report", str(manifest)])
    assert result.exit_code == 0, result.stdout
    artifact = json.loads(result.stdout)
    assert "incident" in artifact["schema"]
    assert artifact["rrn"] == "RRN-000000000099"
    assert artifact["total_incidents"] == 1


def test_incidents_record_requires_rrn_in_manifest(tmp_path, home):
    """A manifest with no rrn errors clearly."""
    no_rrn = """\
---
rcan_version: "3.0"
metadata: { robot_name: anon, manufacturer: x, model: y, firmware_version: "1" }
physics: { type: arm, dof: 6 }
drivers: [{ id: arm, protocol: feetech, port: /dev/null }]
safety: { estop: { software: true, hardware: false, response_ms: 100 } }
capabilities: [navigate]
---
# anon
"""
    p = tmp_path / "ROBOT.md"
    p.write_text(no_rrn)
    result = runner.invoke(
        app,
        [
            "incidents", "record", str(p),
            "--severity", "other",
            "--category", "x",
            "--description", "y",
        ],
    )
    assert result.exit_code != 0
    assert "rrn" in result.stdout.lower() or "rrn" in (result.stderr or "").lower()
