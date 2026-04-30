"""SP-AN Task 2: robot-md://hotplug/pending must appear in build_server's
resources list."""

from __future__ import annotations

import pytest

from robot_md.mcp.context import load_context
from robot_md.mcp.resources.hotplug_pending import URI as HOTPLUG_PENDING_URI
from robot_md.mcp.server import build_server


@pytest.fixture
def server(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    return build_server(ctx)


async def test_hotplug_pending_resource_uri_is_registered(server) -> None:
    resources = await server.list_resources()
    uris = {str(r.uri) for r in resources}
    assert HOTPLUG_PENDING_URI in uris, f"expected {HOTPLUG_PENDING_URI!r}; got {uris!r}"
