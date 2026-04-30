"""Windows Scheduled Task installer — stub.

The full pywin32 implementation is deferred to a SP-HP follow-up so it
can be smoke-tested on a real Windows host. Operators on Windows can
run `robot-md hotplug-daemon start` manually in the meantime.
"""

from __future__ import annotations


def write_scheduled_task() -> None:
    raise NotImplementedError("Windows installer landing in SP-HP follow-up")
