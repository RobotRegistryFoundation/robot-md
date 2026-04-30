from __future__ import annotations

import threading
from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue


def test_concurrent_appenders_all_records_present(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    decision = Decision(tier="LOW", unambiguous=False, bind_proposal=None)

    def append():
        q.append_pending(DeviceEvent(
            kind="tty_added", vid="1a86", pid="7523", serial=None,
            path="/dev/ttyACM0", transport="feetech",
            raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
        ), decision)

    threads = [threading.Thread(target=append) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = (tmp_path / "q.jsonl").read_text().splitlines()
    assert len(lines) == 20
