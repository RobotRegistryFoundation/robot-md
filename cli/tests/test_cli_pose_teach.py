"""CLI: robot-md pose teach <name> <path> writes physics.poses[name]."""
from __future__ import annotations

from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from robot_md.__main__ import app


class _FakeBus:
    def __init__(self) -> None:
        self._torque = False
        self._positions = {"shoulder_pan": 2048, "shoulder_lift": 1600}

    def torque(self, on: bool) -> None:
        self._torque = on

    def read_positions(self) -> dict[str, int]:
        return dict(self._positions)


def test_pose_teach_writes_named_pose(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech, port: /dev/ttyACM0}]\n"
        "capabilities: [status.report]\n"
        "safety: {estop: {software: true, response_ms: 100}}\n"
        "---\n# bob\n"
    )
    runner = CliRunner()
    with patch("robot_md.__main__._open_feetech_bus", return_value=_FakeBus()):
        result = runner.invoke(
            app, ["pose", "teach", "ready", str(manifest), "--yes"]
        )
    assert result.exit_code == 0, result.output
    fm = yaml.safe_load(manifest.read_text().split("---")[1])
    assert fm["physics"]["poses"]["ready"]["joints"]["shoulder_pan"] == 2048
    assert fm["physics"]["poses"]["ready"]["source"] == "taught"
