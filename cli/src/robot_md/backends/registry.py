"""Backend discovery + deterministic resolution."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from importlib.metadata import entry_points

from robot_md.backends.base import CapabilityBackend
from robot_md.robot_spec import RobotSpec

_log = logging.getLogger(__name__)

CORE_CAPABILITY_PREFIXES = frozenset({"arm.", "nav.", "perceive.", "gripper.", "safety."})
_VENDOR_CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z]([a-z0-9_.]*[a-z0-9_])?$")


class BackendRegistrationError(Exception):
    """Raised when a backend declares a malformed capability name."""


def _validate_capability_namespace(backend_name: str, caps: frozenset[str]) -> None:
    """Reject backend registration if any capability is malformed.

    Every capability name must match `<vendor>.<name>` shape:
    `^[a-z][a-z0-9_]*\\.[a-z]([a-z0-9_.]*[a-z0-9_])?$`. Core capabilities
    (`arm.pick`, `nav.go_to`, etc.) match the same regex by design.

    Allowed characters are ASCII lowercase letters, digits, and underscore.
    Multi-dot hierarchies are valid (`acme.robotics.servo`,
    `lerobot.motion.cartesian`) — the vendor is the first component, the
    name is everything after the first dot. The name segment must not
    start or end with a dot.

    `CORE_CAPABILITY_PREFIXES` identifies which prefixes are RRF-canonical
    "core"; downstream consumers (Task 5's `describe_default()`, Task 7's
    `enumerate_capabilities()`) use it for tier classification. A
    well-formed capability whose prefix is not in that set is treated as
    vendor-shaped.

    Args:
        backend_name: entry-point name of the backend being registered;
            used in the error message to identify the offender.
        caps: the set returned from `backend.capabilities()`.

    Raises:
        BackendRegistrationError on first violation.

    Note: the existing feetech_depthai backend declares `vision.describe`
    and `status.report`. Both match the regex (they look like
    <vendor>.<name>) so the registry accepts them as vendor-shaped, even
    though they're shipped in a first-party backend. Do NOT expand
    CORE_CAPABILITY_PREFIXES here — that list is RRF-canonical core only.
    """
    for cap in caps:
        if not _VENDOR_CAPABILITY_PATTERN.match(cap):
            raise BackendRegistrationError(
                f"Backend '{backend_name}' declared capability '{cap}': "
                f"not in <vendor>.<name> form "
                f"(e.g. 'arm.pick', 'lerobot.teleop')."
            )


def discover_backends() -> list[CapabilityBackend]:
    """Load backends registered under the `robot_md.backends` entry-point group.

    Backends with malformed capability names are logged and skipped — the rest
    of the registry continues to load.
    """
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
            instance = cls()
        except Exception as e:  # noqa: BLE001 — adapter import failures are non-fatal
            _log.warning("backend %r failed to load: %s", ep.name, e)
            continue
        try:
            _validate_capability_namespace(ep.name, instance.capabilities())
        except BackendRegistrationError as e:
            _log.warning("%s — skipping backend.", e)
            continue
        out.append(instance)
    return out


@dataclass
class BackendRegistry:
    backends: list[CapabilityBackend] = field(default_factory=list)

    @classmethod
    def from_entry_points(cls) -> BackendRegistry:
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
