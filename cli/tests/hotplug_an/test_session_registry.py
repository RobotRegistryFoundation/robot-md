"""SP-AN v2 SessionRegistry — per-session subscribe/emit semantics.

Replaces the v1 single-active-session capture pattern. Multiple connected
MCP sessions can independently subscribe to robot-md://hotplug/pending,
and each queue change fans out a notifications/resources/updated to
every currently-subscribed session.
"""

from __future__ import annotations

import asyncio

from robot_md.mcp.resource_subscribers import SessionRegistry


class _FakeSession:
    def __init__(self, *, raise_on_emit: bool = False) -> None:
        self.calls: list[str] = []
        self._raise = raise_on_emit

    async def send_resource_updated(self, uri) -> None:
        self.calls.append(str(uri))
        if self._raise:
            raise RuntimeError("session went away")


URI_A = "robot-md://hotplug/pending"
URI_B = "robot-md://other/resource"


def test_emit_routes_to_a_single_subscriber() -> None:
    reg = SessionRegistry()
    s = _FakeSession()
    reg.add(URI_A, s)
    asyncio.run(reg.emit(URI_A))
    assert s.calls == [URI_A]


def test_emit_with_no_subscribers_is_noop() -> None:
    reg = SessionRegistry()
    asyncio.run(reg.emit(URI_A))  # must not raise


def test_emit_fans_out_to_all_subscribers_of_a_uri() -> None:
    reg = SessionRegistry()
    s1, s2 = _FakeSession(), _FakeSession()
    reg.add(URI_A, s1)
    reg.add(URI_A, s2)
    asyncio.run(reg.emit(URI_A))
    assert s1.calls == [URI_A]
    assert s2.calls == [URI_A]


def test_emit_keeps_uris_separate() -> None:
    reg = SessionRegistry()
    a, b = _FakeSession(), _FakeSession()
    reg.add(URI_A, a)
    reg.add(URI_B, b)
    asyncio.run(reg.emit(URI_A))
    assert a.calls == [URI_A]
    assert b.calls == []


def test_remove_drops_session_from_uri() -> None:
    reg = SessionRegistry()
    s = _FakeSession()
    reg.add(URI_A, s)
    reg.remove(URI_A, s)
    asyncio.run(reg.emit(URI_A))
    assert s.calls == []


def test_emit_drops_session_that_raises_so_future_emits_skip_it() -> None:
    reg = SessionRegistry()
    bad = _FakeSession(raise_on_emit=True)
    good = _FakeSession()
    reg.add(URI_A, bad)
    reg.add(URI_A, good)
    asyncio.run(reg.emit(URI_A))
    # bad raised once but is dropped; good still got the event
    assert good.calls == [URI_A]
    asyncio.run(reg.emit(URI_A))
    # second emit reaches good only — bad was evicted
    assert good.calls == [URI_A, URI_A]


def test_add_is_idempotent() -> None:
    reg = SessionRegistry()
    s = _FakeSession()
    reg.add(URI_A, s)
    reg.add(URI_A, s)  # second add must not double-fire
    asyncio.run(reg.emit(URI_A))
    assert s.calls == [URI_A]


def test_remove_unknown_session_is_noop() -> None:
    reg = SessionRegistry()
    s = _FakeSession()
    reg.remove(URI_A, s)  # never subscribed
    asyncio.run(reg.emit(URI_A))
    assert s.calls == []
