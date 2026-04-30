"""inotify wrapper around watchdog. Fires `on_change` whenever the
ROBOT.md file is modified or created. The MCP server uses this to
reload its RobotSpec + emit `notifications/tools/list_changed` so a
freshly-merged hot-plug driver is callable without a server restart.

Cross-platform via watchdog's per-OS backends (inotify on Linux,
kqueue on macOS / BSD, ReadDirectoryChangesW on Windows).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class ManifestWatcher:
    def __init__(
        self,
        *,
        manifest_path: Path,
        on_change: Callable[[], None],
    ) -> None:
        self.manifest_path = manifest_path
        self._observer = Observer()
        self._handler = _Handler(target=manifest_path, on_change=on_change)

    def start(self) -> None:
        self._observer.schedule(
            self._handler, str(self.manifest_path.parent), recursive=False,
        )
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=2.0)


class _Handler(FileSystemEventHandler):
    def __init__(self, *, target: Path, on_change: Callable[[], None]) -> None:
        self._target = target.resolve()
        self._on_change = on_change

    def on_modified(self, event):
        if Path(event.src_path).resolve() == self._target:
            self._on_change()

    def on_created(self, event):
        if Path(event.src_path).resolve() == self._target:
            self._on_change()
