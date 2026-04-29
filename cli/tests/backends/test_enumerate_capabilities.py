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
