from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_status_when_no_daemon_running() -> None:
    """Smoke-test that `robot-md hotplug-daemon status` runs and reports the
    not-running state. Relies on no daemon currently running on the test host;
    if a real daemon is running, this test is meaningless and skipping is fine.
    """
    src = str(Path(__file__).parents[2] / "src")
    env = {
        **os.environ,
        "PYTHONPATH": src + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    pidfile = Path.home() / ".robot-md" / "hotplug-daemon.pid"
    if pidfile.exists():
        import pytest
        pytest.skip(f"a daemon is running (or stale pidfile at {pidfile})")
    proc = subprocess.run(
        [sys.executable, "-m", "robot_md", "hotplug-daemon", "status"],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert (
        "not running" in proc.stdout.lower()
        or "stopped" in proc.stdout.lower()
    )
