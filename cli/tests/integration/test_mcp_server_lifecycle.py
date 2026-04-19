"""Spawn the MCP server as a subprocess, verify startup + tool listing."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

pytestmark = pytest.mark.integration

VENV_PY = "/home/craigm26/opencastor/venv/bin/python3"


def _rpc(proc, body: dict, *, timeout: float = 5.0) -> dict:
    """Send one JSON-RPC request, read one line of response."""
    data = (json.dumps(body) + "\n").encode()
    proc.stdin.write(data)
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read().decode(errors="replace")
        raise RuntimeError(f"empty response; stderr={stderr!r}")
    return json.loads(line.decode())


def _wait_ready(proc, timeout_s: float = 3.0) -> None:
    """No-op — FastMCP answers on first request. Retained for clarity."""
    pass


def test_server_lists_tools(fixtures_dir):
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [
            VENV_PY,
            "-m",
            "robot_md.mcp.server",
            str(fixtures_dir / "robot_md_oak_d_factory_cal.yaml"),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _wait_ready(proc)
        init = _rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
        )
        assert "result" in init, f"initialize failed: {init}"

        # MCP requires an `initialized` notification after initialize
        _note = (
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        ).encode()
        proc.stdin.write(_note)
        proc.stdin.flush()

        listing = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tool_names = {t["name"] for t in listing["result"]["tools"]}
        assert {"render", "validate", "estop"}.issubset(tool_names), (
            f"expected render/validate/estop in tools, got {tool_names}"
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


def test_server_fails_fast_on_bad_manifest(tmp_path):
    bad = tmp_path / "bad.ROBOT.md"
    bad.write_text("no frontmatter here")
    r = subprocess.run(
        [VENV_PY, "-m", "robot_md.mcp.server", str(bad)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert r.returncode != 0, f"expected nonzero exit, got {r.returncode}"
    msg = (r.stderr or "").lower()
    assert "fatal" in msg or "validation" in msg or "parse" in msg, (
        f"expected validation/parse error on stderr, got {r.stderr!r}"
    )
