"""Hardware smoke: drop a `snapshot` command, verify a frame event lands."""

from __future__ import annotations

import json
import time

import pytest

pytestmark = pytest.mark.hardware

pytest.importorskip("depthai")
pytest.importorskip("feetech_servo_sdk")


def test_snapshot_publishes_frame_event(tmp_path, fixtures_dir, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ROBOT_MD_DASHBOARD_DISABLED", raising=False)
    from robot_md.mcp.context import load_context

    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    try:
        cmd = tmp_path / ".robot-md" / "commands.jsonl"
        cmd.parent.mkdir(parents=True, exist_ok=True)
        with cmd.open("a") as f:
            f.write(json.dumps({"cmd": "snapshot"}) + "\n")

        events = tmp_path / ".robot-md" / "events.jsonl"
        deadline = time.time() + 10.0
        frame_seen = False
        while time.time() < deadline and not frame_seen:
            if events.exists():
                for line in events.read_text().splitlines():
                    try:
                        if json.loads(line)["kind"] == "frame":
                            frame_seen = True
                            break
                    except Exception:
                        pass
            time.sleep(0.3)
        assert frame_seen, "no frame event within 10s"
    finally:
        if ctx.publisher:
            ctx.publisher.stop()
