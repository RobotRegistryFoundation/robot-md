# cli/tests/backends/test_capability_namespace_skips_in_discovery.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

from robot_md.backends.base import CapabilityBackend
from robot_md.backends.registry import discover_backends


class _GoodBackend(CapabilityBackend):
    name = "good"
    protocols = frozenset({"feetech"})

    def open(self, spec):
        pass

    def close(self):
        pass

    def capabilities(self) -> frozenset[str]:
        return frozenset({"arm.pick"})

    def execute(self, capability, args, *, dry_run, estop):
        raise NotImplementedError


class _BadBackend(CapabilityBackend):
    name = "bad"
    protocols = frozenset({"feetech"})

    def open(self, spec):
        pass

    def close(self):
        pass

    def capabilities(self) -> frozenset[str]:
        return frozenset({"NOT-VALID"})

    def execute(self, capability, args, *, dry_run, estop):
        raise NotImplementedError


def _fake_entry_points(group: str):
    assert group == "robot_md.backends"
    good_ep = MagicMock()
    good_ep.name = "good"
    good_ep.load.return_value = _GoodBackend
    bad_ep = MagicMock()
    bad_ep.name = "bad"
    bad_ep.load.return_value = _BadBackend
    return [good_ep, bad_ep]


def test_malformed_backend_skipped_others_keep_loading() -> None:
    with patch("robot_md.backends.registry.entry_points", _fake_entry_points):
        out = discover_backends()
    names = sorted(b.name for b in out)
    assert names == ["good"], f"expected only 'good' to load, got {names}"
