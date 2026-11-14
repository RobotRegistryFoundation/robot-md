"""Telling an older robot-md-gateway apart, and the gateway config on #113 installs.

robot-md's MCP stop depends on robot-md-gateway#35: on 0.5.0a9 a stop has to
pass every gate a motion does, and the gateway never stops the arm when
heartbeats stop. The gateway exposes no version that tells the two apart (its
OpenAPI version string is the constant 0.4.0a1 in both), so the server reads
which routes it serves, once, at startup, and warns when the safety routes
are missing.

install-gateway (since robot-md#113) keeps gateway.env and bearers.yaml 0600
for the gateway's own user, so the MCP server can't read them: it then pins
envelopes to the copy of ROBOT.md install-gateway made, and its "no bearer"
refusal says how the person hands it the actuate token.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from robot_md import gateway_client
from robot_md.mcp import server as server_module
from robot_md.mcp.tools.estop import estop_tool
from robot_md.mcp.tools.execute_capability import execute_capability_tool
from tests.conftest import TEST_BEARER
from tests.fake_gateway import OLD_GATEWAY_ROUTES
from tests.unit.test_mcp_motion_through_gateway import _ctx, _free_port

# --------------------------------------------------------------------------
# Which gateway is this?
# --------------------------------------------------------------------------


def _config(url: str) -> gateway_client.GatewayConfig:
    return gateway_client.resolve_config(
        served_manifest_path="/tmp/ROBOT.md",
        frontmatter={},
        environ={gateway_client.ENV_URL: url, gateway_client.ENV_BEARER: TEST_BEARER},
    )


def test_a_gateway_with_the_safety_routes_is_recognized(fake_gateway):
    r = gateway_client.check_gateway_generation(_config(fake_gateway.url))
    assert r["result"] == "has_safety_routes"


def test_an_older_gateway_is_recognized(fake_gateway):
    fake_gateway.routes = OLD_GATEWAY_ROUTES
    r = gateway_client.check_gateway_generation(_config(fake_gateway.url))
    assert r["result"] == "lacks_safety_routes"
    assert "robot-md-gateway#35" in r["detail"]
    assert "does not stop the arm when heartbeats stop" in r["detail"]


def test_nothing_listening_is_unknown():
    r = gateway_client.check_gateway_generation(
        _config(f"http://127.0.0.1:{_free_port()}"), timeout_s=0.5
    )
    assert r["result"] == "unknown"


def test_the_check_reads_openapi_without_the_bearer(fake_gateway):
    gateway_client.check_gateway_generation(_config(fake_gateway.url))
    (request,) = fake_gateway.get_requests
    assert request["path"] == "/openapi.json"
    assert "authorization" not in request["headers"]
    assert fake_gateway.requests == [], "the check sent a POST"


def test_startup_check_warns_in_results_on_an_older_gateway(fixtures_dir, gateway_env, capsys):
    gateway_env.routes = OLD_GATEWAY_ROUTES
    ctx = _ctx(fixtures_dir, extra_caps=("status.report",))
    server_module.start_gateway_check(ctx).join(5)
    assert len(ctx.gateway_warnings) == 1
    assert "robot-md-gateway#35" in capsys.readouterr().err
    motion = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    read = execute_capability_tool(ctx, capability="status.report", args={}, dry_run=False)
    stop = estop_tool(ctx)
    for result in (motion, read, stop):
        assert result["warnings"] == ctx.gateway_warnings
    # A warning, not a refusal: the gateway still decides.
    assert motion["status"] == "ok"


def test_startup_check_says_nothing_on_a_current_gateway(fixtures_dir, gateway_env):
    ctx = _ctx(fixtures_dir)
    server_module.start_gateway_check(ctx).join(5)
    assert ctx.gateway_warnings == []
    r = execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=False)
    assert "warnings" not in r


def test_main_starts_the_check(monkeypatch, fixtures_dir):
    started = []

    class _Server:
        def run(self):
            started.append("run")

    monkeypatch.setattr(
        sys, "argv", ["robot-md-mcp", str(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")]
    )
    monkeypatch.setattr(server_module, "build_server", lambda ctx: _Server())
    monkeypatch.setattr(server_module, "start_gateway_check", lambda ctx: started.append("check"))
    assert server_module.main() == 0
    assert started == ["check", "run"]


# --------------------------------------------------------------------------
# install-gateway's 0600 files
# --------------------------------------------------------------------------


def _unreadable(path: Path) -> None:
    path.write_text("x")
    path.chmod(0)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes")
def test_an_unreadable_bearers_file_says_how_to_hand_over_the_token(tmp_path, monkeypatch):
    import os

    if os.geteuid() == 0:
        pytest.skip("root reads mode-0 files")
    bearers = tmp_path / "bearers.yaml"
    _unreadable(bearers)
    monkeypatch.setattr(gateway_client, "INSTALL_GATEWAY_BEARERS_FILE", bearers)
    config = gateway_client.resolve_config(
        served_manifest_path=tmp_path / "ROBOT.md", frontmatter={}, environ={}
    )
    assert not config.ready
    problem = config.problems[0]
    assert "not readable by this user" in problem
    assert gateway_client.ENV_BEARER in problem
    assert gateway_client.ENV_BEARERS_FILE in problem


def test_the_missing_bearer_problem_names_both_ways(tmp_path):
    config = gateway_client.resolve_config(
        served_manifest_path=tmp_path / "ROBOT.md", frontmatter={}, environ={}
    )
    (problem,) = [p for p in config.problems if "bearer" in p]
    assert gateway_client.ENV_BEARER in problem
    assert gateway_client.ENV_BEARERS_FILE in problem
    assert "actuate" in problem


def test_envelopes_name_install_gateways_manifest_copy_when_gateway_env_is_unreadable(
    tmp_path, monkeypatch
):
    pinned = tmp_path / "etc-robot-md-gateway-ROBOT.md"
    pinned.write_text("---\n---\n")
    monkeypatch.setattr(gateway_client, "INSTALL_GATEWAY_MANIFEST_FILE", pinned)
    config = gateway_client.resolve_config(
        served_manifest_path=tmp_path / "home" / "ROBOT.md",
        frontmatter={},
        environ={gateway_client.ENV_BEARER: TEST_BEARER},
        env_file=tmp_path / "no-gateway.env",
    )
    assert config.manifest_path == str(pinned)
    assert config.manifest_source == "the copy install-gateway pins"


def test_the_manifest_env_var_and_gateway_env_still_come_first(tmp_path, monkeypatch):
    pinned = tmp_path / "pinned-ROBOT.md"
    pinned.write_text("---\n---\n")
    monkeypatch.setattr(gateway_client, "INSTALL_GATEWAY_MANIFEST_FILE", pinned)
    env_file = tmp_path / "gateway.env"
    env_file.write_text("ROBOT_MD_PATH=/srv/robot/ROBOT.md\n")
    config = gateway_client.resolve_config(
        served_manifest_path=tmp_path / "ROBOT.md",
        frontmatter={},
        environ={gateway_client.ENV_BEARER: TEST_BEARER},
        env_file=env_file,
    )
    assert config.manifest_path == "/srv/robot/ROBOT.md"
    config = gateway_client.resolve_config(
        served_manifest_path=tmp_path / "ROBOT.md",
        frontmatter={},
        environ={
            gateway_client.ENV_BEARER: TEST_BEARER,
            gateway_client.ENV_MANIFEST_PATH: "/x/ROBOT.md",
        },
        env_file=env_file,
    )
    assert config.manifest_path == "/x/ROBOT.md"


def test_the_bearer_never_appears_in_the_check_or_its_warning(fake_gateway):
    fake_gateway.routes = OLD_GATEWAY_ROUTES
    r = gateway_client.check_gateway_generation(_config(fake_gateway.url))
    assert TEST_BEARER not in json.dumps(r)
