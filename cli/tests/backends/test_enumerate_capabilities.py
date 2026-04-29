# cli/tests/backends/test_enumerate_capabilities.py
from __future__ import annotations

from robot_md.backends.base import CapabilityBackend
from robot_md.backends.registry import BackendRegistry


class _StubBackend(CapabilityBackend):
    name = "stub"
    protocols = frozenset({"feetech"})

    def open(self, spec):
        pass

    def close(self):
        pass

    def capabilities(self) -> frozenset[str]:
        return frozenset({"arm.pick"})

    def execute(self, capability, args, *, dry_run, estop):
        raise NotImplementedError


def test_iter_classes_yields_name_class_pairs() -> None:
    reg = BackendRegistry(backends=[_StubBackend()])
    pairs = list(reg.iter_classes())
    assert len(pairs) == 1
    name, cls = pairs[0]
    assert name == "stub"
    assert cls is _StubBackend


from robot_md.backends import enumerate_capabilities, Capability


class _SecondStubBackend(CapabilityBackend):
    name = "stub2"
    protocols = frozenset({"realsense"})

    def open(self, spec):
        pass

    def close(self):
        pass

    def capabilities(self) -> frozenset[str]:
        return frozenset({"perceive.rgb", "stub2.vendor_thing"})

    def execute(self, capability, args, *, dry_run, estop):
        raise NotImplementedError


def test_enumerate_capabilities_walks_registry() -> None:
    reg = BackendRegistry(backends=[_StubBackend(), _SecondStubBackend()])
    pairs = enumerate_capabilities(reg)
    # 1 cap from stub + 2 caps from stub2 = 3 pairs.
    assert len(pairs) == 3
    by_backend = {}
    for backend_name, cap in pairs:
        assert isinstance(cap, Capability)
        by_backend.setdefault(backend_name, []).append(cap.name)
    assert sorted(by_backend["stub"]) == ["arm.pick"]
    assert sorted(by_backend["stub2"]) == ["perceive.rgb", "stub2.vendor_thing"]


def test_enumerate_capabilities_uses_describe_capabilities_override() -> None:
    """If a backend overrides describe_capabilities(), that wins over the default."""
    custom_cap = Capability(
        name="lerobot.teleop",
        namespace="vendor",
        arg_schema={"type": "object", "properties": {"leader_port": {"type": "string"}}},
        description="Drive follower from leader.",
    )

    class _OverrideBackend(_StubBackend):
        name = "override"

        def capabilities(self) -> frozenset[str]:
            return frozenset({"lerobot.teleop"})

        def describe_capabilities(self) -> list[Capability]:
            return [custom_cap]

    reg = BackendRegistry(backends=[_OverrideBackend()])
    pairs = enumerate_capabilities(reg)
    assert len(pairs) == 1
    backend_name, cap = pairs[0]
    assert backend_name == "override"
    assert cap is custom_cap  # exact object — override wins
