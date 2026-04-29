"""Integration: verify `discover` emits MCP progress notifications per step."""

from __future__ import annotations

import json
import os
import select
import site
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

VENV_PY = sys.executable


def _build_env(home: Path) -> dict:
    """Build subprocess env with HOME override that still resolves robot_md.

    HOME override hides the real user's user-site (where robot_md's editable
    install .pth and the `mcp` SDK live). Propagate both the repo src dir and
    the parent's sys.path to the subprocess via PYTHONPATH so imports still
    resolve. Mirrors the pattern in test_mcp_server_backfill.py::_spawn.
    """
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["HOME"] = str(home)
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    parent_paths = [src_dir, site.getusersitepackages()] + [p for p in site.getsitepackages() if p]
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        [p for p in parent_paths if p] + ([existing_pp] if existing_pp else [])
    )
    return env


def _send(proc, body: dict) -> None:
    proc.stdin.write((json.dumps(body) + "\n").encode())
    proc.stdin.flush()


def _read_until_response(proc, request_id: int, timeout_s: float = 5.0):
    """Read lines until we get the reply with id == request_id.
    Returns (reply_dict, list_of_progress_notifications)."""
    import time

    progress: list[dict] = []
    end = time.time() + timeout_s
    while time.time() < end:
        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if not ready:
            continue
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("stream closed before reply")
        msg = json.loads(line.decode())
        if msg.get("method") == "notifications/progress":
            progress.append(msg["params"])
            continue
        if msg.get("id") == request_id:
            return msg, progress
    raise TimeoutError(f"no reply for id={request_id} within {timeout_s}s")


def test_discover_emits_per_step_progress(fixtures_dir, tmp_path):
    manifest = fixtures_dir / "robot_md_oak_d_factory_cal.yaml"
    env = _build_env(tmp_path)
    proc = subprocess.Popen(
        [VENV_PY, "-m", "robot_md.mcp.server", str(manifest)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _send(
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
        try:
            _read_until_response(proc, 1)
        except RuntimeError:
            err = proc.stderr.read().decode(errors="replace")
            raise RuntimeError(f"server died; stderr:\n{err}") from None
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        # Two steps -> expect at least 2 progress notifications.
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 42,
                "method": "tools/call",
                "params": {
                    "name": "discover",
                    "arguments": {"steps": [{"capture": {}}, {"detect": {"descriptors": []}}]},
                    "_meta": {"progressToken": "tok-42"},
                },
            },
        )
        # 90s budget — github-hosted CI runners on Python 3.12/3.13 are
        # consistently slower at MCP stdio child startup + multi-step discover
        # dispatch than 3.10/3.11. 10s flaked ~30% on the matrix; 30s flaked
        # 100% on 3.12/3.13 (issue #19). 90s gives headroom across all four
        # Python versions without inflating CI duration in the green case.
        reply, progress = _read_until_response(proc, 42, timeout_s=90.0)
        assert "result" in reply, f"discover call failed: {reply}"
        # Every progress notification for this call must carry the token.
        for p in progress:
            assert p.get("progressToken") == "tok-42"
        # At least 2 notifications (one per step). Allow more because
        # FastMCP may emit begin + complete frames.
        assert len(progress) >= 2, f"expected >=2 progress notifications, got {progress}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
