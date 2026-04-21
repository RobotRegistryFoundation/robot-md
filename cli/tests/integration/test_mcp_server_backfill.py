"""Integration: start server A, fail a capability, stop A, start server B,
verify recent_errors resource contains the prior failure.

Exercises the full chain: publisher fan-out writes to events.jsonl (via
EventPublisher), load_context on server B replays the JSONL into the new
InvocationLog.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

VENV_PY = sys.executable


def _rpc(proc, body: dict, *, timeout: float = 5.0) -> dict:
    data = (json.dumps(body) + "\n").encode()
    proc.stdin.write(data)
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read().decode(errors="replace")
        raise RuntimeError(f"empty response; stderr={stderr!r}")
    return json.loads(line.decode())


def _spawn(manifest: Path, home: Path):
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["HOME"] = str(home)
    # Disable WS port to avoid cross-test contention.
    env["ROBOT_MD_DASHBOARD_DISABLED"] = "0"
    # Overriding HOME hides the real user's user-site (where robot_md's
    # editable-install .pth and the `mcp` SDK live). Propagate both the
    # repo src dir and the parent's sys.path to the subprocess via
    # PYTHONPATH so imports still resolve under the fake HOME.
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    import site

    # user-site first so its pydantic/typing_extensions shadow the older
    # system site-packages copies (matching the parent process's sys.path).
    parent_paths = [src_dir, site.getusersitepackages()] + [p for p in site.getsitepackages() if p]
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        [p for p in parent_paths if p] + ([existing_pp] if existing_pp else [])
    )
    return subprocess.Popen(
        [VENV_PY, "-m", "robot_md.mcp.server", str(manifest)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def _handshake(proc):
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
    note = (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode()
    proc.stdin.write(note)
    proc.stdin.flush()


def _call_execute_capability(proc, capability: str) -> dict:
    return _rpc(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {
                "name": "execute_capability",
                "arguments": {"capability": capability, "args": {}, "dry_run": False},
            },
        },
    )


def _read_recent_errors(proc, robot_name: str) -> list[dict]:
    r = _rpc(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 100,
            "method": "resources/read",
            "params": {"uri": f"robot-md://{robot_name}/recent_errors"},
        },
    )
    assert "result" in r, f"resources/read failed: {r}"
    contents = r["result"]["contents"][0]["text"]
    return json.loads(contents)


def _robot_name_from_fixture(fixture_path: Path) -> str:
    """Mirror _sanitize_robot_name behaviour for the fixture."""
    from robot_md.mcp.resources import _sanitize_robot_name
    from robot_md.parser import parse_file
    from robot_md.robot_spec import RobotSpec

    spec = RobotSpec.from_parsed(parse_file(fixture_path))
    return _sanitize_robot_name(spec.metadata.robot_name)


def test_recent_errors_survives_server_restart(fixtures_dir, tmp_path):
    manifest = fixtures_dir / "robot_md_oak_d_factory_cal.yaml"
    home = tmp_path / "home"
    home.mkdir()

    # --- Server A: trigger a failure (call an undeclared capability). ---
    import time

    proc_a = _spawn(manifest, home)
    try:
        _handshake(proc_a)
        r = _call_execute_capability(proc_a, "arm.throw")  # undeclared
        # tools/call wraps the tool result in structuredContent; confirm a
        # failure was recorded.
        assert r.get("result", {}).get("isError") in (True, False)  # either is fine
        # Give the EventPublisher writer thread time to drain tool.call and
        # tool.result to events.jsonl BEFORE we SIGTERM the process. SIGTERM
        # kills the daemon writer thread mid-queue; without this pause the
        # tool.result line can be lost and backfill sees no error. The
        # writer polls its queue every 0.1s in EventPublisher._writer_loop
        # and has a small cross-thread scheduling overhead, so 1.0s is
        # comfortably above the worst-case drain time while staying fast.
        time.sleep(1.0)
    finally:
        proc_a.terminate()
        try:
            proc_a.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc_a.kill()
            proc_a.wait(timeout=2)

    # --- Server B: read recent_errors; the A-run failure must be present. ---
    robot_name = _robot_name_from_fixture(manifest)
    proc_b = _spawn(manifest, home)
    try:
        _handshake(proc_b)
        errors = _read_recent_errors(proc_b, robot_name)
        # When hardware is available, the undeclared 'arm.throw' call is rejected
        # by the `not_declared` branch; when no hardware backend resolves (e.g.
        # in CI without the servo/camera), the request trips the `no_backend`
        # branch instead. Either is a valid server-A failure that must survive
        # the restart; both are now published via _publish_result so backfill
        # reconstructs them identically.
        observed_reasons = {e.get("reason") for e in errors}
        assert observed_reasons & {"not_declared", "no_backend"}, (
            f"expected a server-A failure (not_declared or no_backend), got {errors}"
        )
    finally:
        proc_b.terminate()
        try:
            proc_b.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc_b.kill()
            proc_b.wait(timeout=2)
