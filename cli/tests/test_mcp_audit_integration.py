"""P3: Audit-log integration on the MCP capability gate.

Whenever the MCP server's execute_capability tool returns a result —
allow, hitl_gate denial, estop block, precondition fail, busy — an
entry must land in the per-robot hash-chained audit log. This is the
"every safety-relevant decision is recorded" property an EU AI Act
notified body would check.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

import pytest

from robot_md.audit import load_entries, verify_chain


class _FakeBackend:
    name = "fake"
    protocols = frozenset({"feetech"})
    read_only_capabilities = frozenset()

    def open(self, spec):
        self.spec = spec

    def close(self):
        pass

    def capabilities(self):
        return frozenset({"arm.pick", "arm.place"})

    def execute(self, capability, args, *, dry_run, estop):
        from robot_md.backends.base import ExecutionEvent, ExecutionResult

        return ExecutionResult(
            status="ok",
            trajectory=[],
            events=[ExecutionEvent(kind="plan", data={"cap": capability})],
            error=None,
        )


@dataclass
class _Metadata:
    rrn: str | None = "RRN-000000000099"


@dataclass
class _Safety:
    hitl_gates: list = field(default_factory=list)


@dataclass
class _CapContract:
    preconditions: list = field(default_factory=list)


@dataclass
class _Spec:
    capabilities: frozenset = field(default_factory=lambda: frozenset({"arm.pick"}))
    metadata: _Metadata = field(default_factory=_Metadata)
    safety: _Safety = field(default_factory=_Safety)
    capability_contracts: dict = field(default_factory=dict)


class _Estop:
    def __init__(self, on=False):
        self._on = on

    def is_set(self):
        return self._on

    def set(self):
        self._on = True


@dataclass
class _Ctx:
    spec: _Spec
    backend: _FakeBackend
    estop: _Estop
    exec_lock: Lock = field(default_factory=Lock)
    publisher: object = None


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def ctx() -> _Ctx:
    spec = _Spec()
    backend = _FakeBackend()
    backend.open(spec)
    return _Ctx(spec=spec, backend=backend, estop=_Estop())


def test_successful_invocation_records_audit_entry(ctx, home):
    from robot_md.mcp.tools.execute_capability import execute_capability_tool

    r = execute_capability_tool(
        ctx, capability="arm.pick", args={}, dry_run=True, confirm_token=None
    )
    assert r["status"] == "ok"

    entries = load_entries("RRN-000000000099")
    assert len(entries) == 1
    e = entries[0]
    assert e["event"] == "capability_invocation"
    assert e["details"]["capability"] == "arm.pick"
    assert e["details"]["status"] == "ok"


def test_hitl_gate_denial_records_audit_entry(ctx, home):
    """Manifest declares hitl_gate require_auth on `arm` scope; invoke without
    a confirm_token; expect denial AND audit entry with reason=hitl_gate."""
    ctx.spec.safety.hitl_gates = [{"scope": "arm", "require_auth": True}]
    from robot_md.mcp.tools.execute_capability import execute_capability_tool

    r = execute_capability_tool(
        ctx, capability="arm.pick", args={}, dry_run=True, confirm_token=None
    )
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "hitl_gate"

    entries = load_entries("RRN-000000000099")
    assert len(entries) == 1
    e = entries[0]
    assert e["details"]["reason"] == "hitl_gate"
    assert e["details"]["scope"] == "arm"


def test_estop_set_records_audit_entry(ctx, home):
    ctx.estop.set()
    from robot_md.mcp.tools.execute_capability import execute_capability_tool

    r = execute_capability_tool(
        ctx, capability="arm.pick", args={}, dry_run=True, confirm_token=None
    )
    assert r["status"] == "blocked"
    assert r["error"]["reason"] == "estop_set"

    entries = load_entries("RRN-000000000099")
    assert len(entries) == 1
    assert entries[0]["details"]["reason"] == "estop_set"


def test_audit_chain_remains_valid_across_multiple_invocations(ctx, home):
    from robot_md.mcp.tools.execute_capability import execute_capability_tool

    # Three invocations: ok, denied, ok
    execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=True, confirm_token=None)
    ctx.spec.safety.hitl_gates = [{"scope": "arm", "require_auth": True}]
    execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=True, confirm_token=None)
    ctx.spec.safety.hitl_gates = []
    execute_capability_tool(ctx, capability="arm.pick", args={}, dry_run=True, confirm_token=None)

    result = verify_chain("RRN-000000000099")
    assert result["valid"] is True
    assert result["entries"] == 3


def test_no_audit_when_manifest_has_no_rrn(home):
    """Unregistered robots can still use the MCP — no audit log written.

    EU AI Act compliance binds to RRN; an unregistered manifest has no
    chain to bind audits to. Behaviour: silent no-op, never crash.
    """
    spec = _Spec(metadata=_Metadata(rrn=None))
    backend = _FakeBackend()
    backend.open(spec)
    ctx_no_rrn = _Ctx(spec=spec, backend=backend, estop=_Estop())

    from robot_md.mcp.tools.execute_capability import execute_capability_tool

    r = execute_capability_tool(
        ctx_no_rrn, capability="arm.pick", args={}, dry_run=True, confirm_token=None
    )
    assert r["status"] == "ok"
    # No log file should exist anywhere under HOME for any rrn
    audit_dir = home / ".robot-md" / "audit"
    assert not audit_dir.exists() or not any(audit_dir.iterdir())


def test_estop_set_records_audit_entry(ctx, home):
    """Setting the software e-stop is a reactive-safety action — must audit."""
    from robot_md.mcp.tools.estop import estop_tool

    # ctx.estop needs a real .set() returning a timestamp; build a stub
    class _RealEstop:
        def __init__(self):
            self._on = False
            self._set_at = None

        def set(self):
            import time
            self._on = True
            self._set_at = time.time()
            return self._set_at

        def clear(self):
            self._on = False

        def is_set(self):
            return self._on

    ctx.estop = _RealEstop()
    r = estop_tool(ctx)
    assert r["ok"] is True

    entries = load_entries("RRN-000000000099")
    assert len(entries) == 1
    assert entries[0]["event"] == "estop_set"


def test_estop_clear_records_audit_entry(ctx, home):
    """Clearing the e-stop is also recorded — and denied clears too."""
    import time

    class _RealEstop:
        def __init__(self):
            self._on = True

        def set(self):
            self._on = True
            return time.time()

        def clear(self):
            self._on = False

        def is_set(self):
            return self._on

    ctx.estop = _RealEstop()

    # Manifest declares system HITL gate → clear without token must be denied + audited
    ctx.spec.safety.hitl_gates = [{"scope": "system", "require_auth": True}]
    from robot_md.mcp.tools.estop import estop_clear_tool

    r1 = estop_clear_tool(ctx, confirm_token=None)
    assert r1["ok"] is False
    assert r1["error"]["reason"] == "hitl_gate"

    # With token: clear succeeds, also audited
    r2 = estop_clear_tool(ctx, confirm_token="operator-ack")
    assert r2["ok"] is True

    entries = load_entries("RRN-000000000099")
    assert len(entries) == 2
    assert entries[0]["event"] == "estop_clear_denied"
    assert entries[0]["details"]["reason"] == "hitl_gate"
    assert entries[1]["event"] == "estop_cleared"


def test_audit_failure_never_crashes_capability_call(ctx, home, monkeypatch):
    """If audit.record_event raises (disk full, etc.), the capability call
    must still complete. Audit integrity is checked separately by `audit verify`."""
    import robot_md.mcp.tools.execute_capability as mod_under_test

    def boom(*_a, **_kw):
        raise RuntimeError("simulated audit failure")

    # Patch the import inside _audit_invocation
    import robot_md.audit as audit_mod
    monkeypatch.setattr(audit_mod, "record_event", boom)

    from robot_md.mcp.tools.execute_capability import execute_capability_tool

    r = execute_capability_tool(
        ctx, capability="arm.pick", args={}, dry_run=True, confirm_token=None
    )
    assert r["status"] == "ok"  # call succeeded despite audit failure
