# cli/tests/backends/test_describe_capabilities_cli.py
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_describe_capabilities_json_output_lists_feetech_caps() -> None:
    cmd = [
        sys.executable,
        "-m",
        "robot_md",
        "describe-capabilities",
        "--json",
    ]
    env = {"PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**env}, check=False)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    # feetech_depthai is the in-tree default; should appear with its caps.
    by_backend = {entry["backend"]: entry for entry in payload}
    assert "feetech_depthai" in by_backend
    cap_names = {c["name"] for c in by_backend["feetech_depthai"]["capabilities"]}
    assert "arm.pick" in cap_names
    assert "vision.describe" in cap_names


def test_describe_capabilities_text_output_groups_by_namespace() -> None:
    cmd = [sys.executable, "-m", "robot_md", "describe-capabilities"]
    env = {"PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**env}, check=False)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "feetech_depthai" in out
    assert "core" in out  # section header for core capabilities
    assert "vendor" in out
    assert "arm.pick" in out
