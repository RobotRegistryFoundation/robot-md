from __future__ import annotations

from robot_md.backends.base import (
    CapabilityBackend,
    ExecutionResult,
)
from robot_md.backends.registry import BackendRegistry
from robot_md.parser import parse_file
from robot_md.robot_spec import RobotSpec


class _Zeta(CapabilityBackend):
    name = "zeta"
    protocols = frozenset({"feetech", "depthai"})

    def open(self, spec): self._spec = spec
    def close(self): pass
    def capabilities(self): return frozenset({"arm.pick"})
    def execute(self, capability, args, *, dry_run, estop):
        return ExecutionResult(status="ok", trajectory=None, events=[], error=None)


class _Alpha(CapabilityBackend):
    name = "alpha"
    protocols = frozenset({"feetech"})

    def open(self, spec): pass
    def close(self): pass
    def capabilities(self): return frozenset({"arm.reach"})
    def execute(self, capability, args, *, dry_run, estop):
        return ExecutionResult(status="ok", trajectory=None, events=[], error=None)


def test_registry_alphabetical_resolution(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    spec = RobotSpec.from_parsed(parsed)
    reg = BackendRegistry(backends=[_Zeta(), _Alpha()])
    backends = reg.resolve(spec)
    # feetech: alphabetical 'alpha' < 'zeta', so alpha wins
    # depthai: only zeta claims it, so zeta
    assert backends["arm_servos"].name == "alpha"
    assert backends["oak-d-1"].name == "zeta"


def test_registry_forces_backend_via_drivers_backend_field(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["drivers"][0]["backend"] = "zeta"
    spec = RobotSpec.from_parsed(parsed)
    reg = BackendRegistry(backends=[_Zeta(), _Alpha()])
    backends = reg.resolve(spec)
    assert backends["arm_servos"].name == "zeta"


def test_registry_unresolved_protocol_maps_to_none(fixtures_dir):
    """When no registered backend claims a driver's protocol, resolve returns None for it."""
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["drivers"][0]["protocol"] = "unknown_protocol"
    spec = RobotSpec.from_parsed(parsed)
    reg = BackendRegistry(backends=[_Zeta()])
    backends = reg.resolve(spec)
    assert backends["arm_servos"] is None


def test_scene_describe_default_returns_empty():
    """CapabilityBackend.scene_describe returns an empty snapshot by default."""
    class _Stub(CapabilityBackend):
        name = "stub"
        protocols = frozenset()
        def open(self, spec): pass
        def close(self): pass
        def capabilities(self): return frozenset()
        def execute(self, capability, args, *, dry_run, estop):
            return ExecutionResult(status="ok", trajectory=None, events=[], error=None)

    snap = _Stub().scene_describe()
    assert snap.frame is None
    assert snap.detections == ()
    assert snap.joint_state == {}


def test_abstract_cannot_instantiate():
    """ABC enforcement — CapabilityBackend can't be instantiated directly."""
    import pytest
    with pytest.raises(TypeError):
        CapabilityBackend()
