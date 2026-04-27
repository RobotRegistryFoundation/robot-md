"""SP1 hardware tests — front-loaded + lazy demo paths against bob's RPi5.

Marked @hardware so they're skipped in CI. Run only on bob:
  pytest tests/hardware/test_sp1_demo_path.py --run-hardware -v
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.hardware


@pytest.mark.skipif(
    not Path("/dev/ttyACM0").exists() or not shutil.which("robot-md"),
    reason="needs bob's feetech bus at /dev/ttyACM0 AND robot-md CLI on PATH",
)
def test_sp1_python_mcp_server_starts_and_lists_tools():
    """The robot-md mcp command starts and exposes execute_task in its
    tool list when given bob's ROBOT.md via cwd-walk."""
    bob_dir = Path.home() / "bob"
    if not (bob_dir / "ROBOT.md").exists():
        pytest.skip("bob's ROBOT.md not at ~/bob/")

    try:
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
    except ImportError:
        pytest.skip("mcp client SDK not installed")

    params = StdioServerParameters(
        command="robot-md",
        args=["mcp"],
        cwd=str(bob_dir),
    )

    async def _check_tools():
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            tool_names = {t.name for t in tools.tools}
            # Must include the SP1-promised motion tools.
            assert "execute_task" in tool_names, f"got: {tool_names}"
            assert "execute_capability" in tool_names, f"got: {tool_names}"
            assert "vision_find" in tool_names, f"got: {tool_names}"
            # Plus the existing manifest tools.
            assert "validate" in tool_names, f"got: {tool_names}"

    asyncio.run(_check_tools())


@pytest.mark.skipif(
    not shutil.which("robot-md"),
    reason="robot-md CLI not on PATH (front-loaded path simulates Python pre-installed)",
)
def test_sp1_lazy_recovery_simulated():
    """Simulates the lazy-discovery path post-pip-install: a fresh
    `robot-md mcp` invocation succeeds. We can't fully simulate /mcp
    Reconnect from pytest, so this verifies the deterministic part:
    spawn the server fresh and confirm it starts without crashing."""
    bob_dir = Path.home() / "bob"
    if not (bob_dir / "ROBOT.md").exists():
        pytest.skip("bob's ROBOT.md not at ~/bob/")

    try:
        result = subprocess.run(
            ["robot-md", "mcp", str(bob_dir / "ROBOT.md")],
            capture_output=True,
            timeout=2,
        )
        # Server exited on its own before timeout — check it wasn't a crash.
        if result.returncode != 0:
            pytest.fail(
                f"robot-md mcp crashed: exit={result.returncode}, "
                f"stderr={result.stderr.decode()[:500]}"
            )
    except subprocess.TimeoutExpired:
        # Server still running after 2s — this is the expected success case.
        pass


@pytest.mark.skipif(
    not Path("/dev/ttyACM0").exists() or not shutil.which("robot-md"),
    reason="needs bob's feetech bus at /dev/ttyACM0 AND robot-md CLI on PATH",
)
def test_sp1_cwd_walk_works_from_subdir():
    """The cwd-walk in `robot-md mcp` must find ROBOT.md from a subdirectory.

    This protects the plugin's no-arg invocation when Claude Code spawns
    the MCP server from any path under the project root."""
    bob_dir = Path.home() / "bob"
    if not (bob_dir / "ROBOT.md").exists():
        pytest.skip("bob's ROBOT.md not at ~/bob/")

    # Look for a subdirectory we can chdir into.
    subdir = None
    for child in bob_dir.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            subdir = child
            break
    if subdir is None:
        pytest.skip("no usable subdirectory under ~/bob/")

    # Run robot-md mcp from the subdirectory; cwd-walk should find ../ROBOT.md.
    try:
        result = subprocess.run(
            ["robot-md", "mcp"],
            capture_output=True,
            timeout=2,
            cwd=str(subdir),
        )
        # Server exited on its own before timeout — check it wasn't a crash.
        if result.returncode != 0:
            pytest.fail(
                f"cwd-walk failed from {subdir}: exit={result.returncode}, "
                f"stderr={result.stderr.decode()[:500]}"
            )
    except subprocess.TimeoutExpired:
        # Server still running after 2s — this is the expected success case.
        pass
