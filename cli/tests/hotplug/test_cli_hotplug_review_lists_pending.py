from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_review_lists_pending_table() -> None:
    """Smoke-test `robot-md hotplug review` runs cleanly. Real fixtures land
    in the integration test (Task 23); here we only assert the command
    doesn't crash and prints either the table header or the empty-queue
    fallback.
    """
    src = str(Path(__file__).parents[2] / "src")
    env = {
        **os.environ,
        "PYTHONPATH": src + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "robot_md", "hotplug", "review"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "event_id" in proc.stdout.lower() or "no pending" in proc.stdout.lower()
