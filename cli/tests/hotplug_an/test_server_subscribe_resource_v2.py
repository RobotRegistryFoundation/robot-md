"""SP-AN v2 integration tests — server.build_server advertises
resources.subscribe=True and dispatches resources/subscribe handlers
through to the SessionRegistry, which fans out
notifications/resources/updated on queue change.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import anyio
import mcp.types as types
from mcp.shared.memory import create_connected_server_and_client_session

from robot_md.mcp.context import McpContext
from robot_md.mcp.resources.hotplug_pending import URI as HOTPLUG_URI
from robot_md.mcp.server import build_server


def _make_minimal_ctx(tmp_path: Path) -> McpContext:
    ctx = MagicMock(spec=McpContext)
    ctx.spec = None
    ctx.manifest_path = tmp_path / "ROBOT.md"
    return ctx


def _capture_resource_updated(received: list) -> object:
    """Build a message_handler that appends ResourceUpdatedNotification roots."""

    async def handler(message):
        if isinstance(message, types.ServerNotification) and isinstance(
            message.root, types.ResourceUpdatedNotification
        ):
            received.append(message.root)

    return handler


async def _send_subscribe(client, uri: str) -> None:
    await client.send_request(
        types.ClientRequest(
            types.SubscribeRequest(
                method="resources/subscribe",
                params=types.SubscribeRequestParams(uri=uri),
            )
        ),
        types.EmptyResult,
    )


async def _send_unsubscribe(client, uri: str) -> None:
    await client.send_request(
        types.ClientRequest(
            types.UnsubscribeRequest(
                method="resources/unsubscribe",
                params=types.UnsubscribeRequestParams(uri=uri),
            )
        ),
        types.EmptyResult,
    )


def test_initialize_advertises_resources_subscribe_true(tmp_path: Path) -> None:
    ctx = _make_minimal_ctx(tmp_path)
    server = build_server(ctx)

    async def main():
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            init_result = await client.initialize()
            assert init_result.capabilities.resources is not None
            assert init_result.capabilities.resources.subscribe is True

    anyio.run(main)


def test_subscribe_then_emit_delivers_notification(tmp_path: Path) -> None:
    ctx = _make_minimal_ctx(tmp_path)
    server = build_server(ctx)
    received: list = []

    async def main():
        async with create_connected_server_and_client_session(
            server._mcp_server,
            message_handler=_capture_resource_updated(received),
        ) as client:
            await client.initialize()
            await _send_subscribe(client, HOTPLUG_URI)
            await server._span_registry.emit(HOTPLUG_URI)
            for _ in range(50):
                if received:
                    break
                await anyio.sleep(0.02)

    anyio.run(main)
    assert received, "client never received the notification"
    assert str(received[0].params.uri) == HOTPLUG_URI


def test_unsubscribe_stops_notifications(tmp_path: Path) -> None:
    ctx = _make_minimal_ctx(tmp_path)
    server = build_server(ctx)
    received: list = []

    async def main():
        async with create_connected_server_and_client_session(
            server._mcp_server,
            message_handler=_capture_resource_updated(received),
        ) as client:
            await client.initialize()
            await _send_subscribe(client, HOTPLUG_URI)
            await _send_unsubscribe(client, HOTPLUG_URI)
            await server._span_registry.emit(HOTPLUG_URI)
            await anyio.sleep(0.2)

    anyio.run(main)
    assert received == [], f"expected no notifications after unsubscribe, got {received}"


def test_two_sessions_both_get_notification_after_subscribing(tmp_path: Path) -> None:
    """The fan-out promise: with two connected, subscribed sessions, one
    registry.emit() reaches both."""
    ctx = _make_minimal_ctx(tmp_path)
    server = build_server(ctx)
    received_a: list = []
    received_b: list = []

    async def main():
        async with create_connected_server_and_client_session(
            server._mcp_server,
            message_handler=_capture_resource_updated(received_a),
        ) as client_a:
            await client_a.initialize()
            await _send_subscribe(client_a, HOTPLUG_URI)

            async with create_connected_server_and_client_session(
                server._mcp_server,
                message_handler=_capture_resource_updated(received_b),
            ) as client_b:
                await client_b.initialize()
                await _send_subscribe(client_b, HOTPLUG_URI)
                await server._span_registry.emit(HOTPLUG_URI)
                for _ in range(50):
                    if received_a and received_b:
                        break
                    await anyio.sleep(0.02)

    anyio.run(main)
    assert received_a, "client A never received the notification"
    assert received_b, "client B never received the notification"


def test_resubscribe_restores_delivery(tmp_path: Path) -> None:
    """Subscribe → unsubscribe → subscribe again — second subscribe
    re-arms delivery."""
    ctx = _make_minimal_ctx(tmp_path)
    server = build_server(ctx)
    received: list = []

    async def main():
        async with create_connected_server_and_client_session(
            server._mcp_server,
            message_handler=_capture_resource_updated(received),
        ) as client:
            await client.initialize()
            await _send_subscribe(client, HOTPLUG_URI)
            await _send_unsubscribe(client, HOTPLUG_URI)
            await _send_subscribe(client, HOTPLUG_URI)
            await server._span_registry.emit(HOTPLUG_URI)
            for _ in range(50):
                if received:
                    break
                await anyio.sleep(0.02)

    anyio.run(main)
    assert received, "resubscribe failed — no notification arrived"
