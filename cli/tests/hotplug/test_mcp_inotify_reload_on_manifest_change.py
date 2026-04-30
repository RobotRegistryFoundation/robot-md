from __future__ import annotations

import time
from pathlib import Path

from robot_md.mcp.manifest_watcher import ManifestWatcher


def test_watcher_fires_on_change(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nid: RRN-test\n---\n")
    received: list = []
    w = ManifestWatcher(manifest_path=manifest, on_change=lambda: received.append(1))
    w.start()
    try:
        time.sleep(0.2)
        manifest.write_text("---\nid: RRN-test\nmetadata:\n  author: a@b\n---\n")
        time.sleep(0.5)
    finally:
        w.stop()
    assert received, "ManifestWatcher did not observe the change"
