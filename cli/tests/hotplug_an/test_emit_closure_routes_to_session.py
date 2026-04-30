"""SP-AN Task 3 (closure half): make_an_emit looks up the captured session
and calls send_resource_updated(URI). Stale-session handling clears the
capture so the next resource read can refresh."""

from __future__ import annotations

import asyncio

from robot_md.mcp.resource_subscribers import make_an_emit
from robot_md.mcp.resources.hotplug_pending import URI


class _FakeSession:
    def __init__(self, *, raise_on_emit: bool = False) -> None:
        self.calls: list[str] = []
        self._raise = raise_on_emit

    async def send_resource_updated(self, uri) -> None:
        self.calls.append(str(uri))
        if self._raise:
            raise RuntimeError("session went away")


def test_emit_calls_send_resource_updated_with_uri() -> None:
    state: dict = {"active_session": _FakeSession()}
    emit = make_an_emit(state, URI)
    asyncio.run(emit())
    assert state["active_session"].calls == [URI]


def test_emit_no_op_when_no_session_captured() -> None:
    state: dict = {"active_session": None}
    emit = make_an_emit(state, URI)
    asyncio.run(emit())  # must not raise


def test_emit_clears_capture_when_session_throws() -> None:
    sess = _FakeSession(raise_on_emit=True)
    state: dict = {"active_session": sess}
    emit = make_an_emit(state, URI)
    asyncio.run(emit())
    assert state["active_session"] is None
