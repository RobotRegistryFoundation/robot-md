"""Backend discovery + deterministic resolution."""

from __future__ import annotations

from dataclasses import dataclass, field

from robot_md.backends.base import CapabilityBackend
from robot_md.robot_spec import RobotSpec


def discover_backends() -> list[CapabilityBackend]:
    """Load backends registered under the `robot_md.backends` entry-point group."""
    try:
        from importlib.metadata import entry_points
    except Exception:
        return []
    try:
        eps = entry_points(group="robot_md.backends")
    except TypeError:
        # Python 3.9 compatibility fallback — not expected here, but harmless.
        all_eps = entry_points()
        eps = all_eps.get("robot_md.backends", []) if hasattr(all_eps, "get") else []
    out: list[CapabilityBackend] = []
    for ep in sorted(eps, key=lambda e: e.name):
        try:
            cls = ep.load()
            out.append(cls())
        except Exception:
            continue
    return out


@dataclass
class BackendRegistry:
    backends: list[CapabilityBackend] = field(default_factory=list)

    @classmethod
    def from_entry_points(cls) -> "BackendRegistry":
        return cls(backends=discover_backends())

    def resolve(self, spec: RobotSpec) -> dict[str, CapabilityBackend | None]:
        """Return {driver_id: backend-or-None} for every driver in the spec.

        Resolution rules:
          1. If `drivers[].backend` names a registered backend, it wins.
          2. Otherwise, the first backend (alphabetical by `.name`) whose
             `.protocols` set includes this driver's protocol wins.
        """
        out: dict[str, CapabilityBackend | None] = {}
        by_name = {b.name: b for b in self.backends}
        ordered = sorted(self.backends, key=lambda b: b.name)
        for drv in spec.drivers:
            if drv.backend and drv.backend in by_name:
                out[drv.id] = by_name[drv.backend]
                continue
            match = next((b for b in ordered if drv.protocol in b.protocols), None)
            out[drv.id] = match
        return out
