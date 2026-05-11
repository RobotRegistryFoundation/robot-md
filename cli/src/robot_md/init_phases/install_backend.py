"""Init phase: auto-install backend packages based on detected hardware.

Runs after `write_manifest` and before `register`. Reads the autodetect scan,
determines which backend packages (so-arm101-actuator, oak-d-actuator, …)
should be present, and pip-installs them. PEP 668 aware.

Failure on install is fatal to the init flow (the manifest references devices
the operator can't actually use without the backend).
"""

from __future__ import annotations

import os  # noqa: F401
import subprocess  # noqa: F401
import sys
from dataclasses import dataclass
from pathlib import Path  # noqa: F401

from robot_md.autodetect import Device
from robot_md.init_phases import PhaseResult  # noqa: F401


@dataclass(frozen=True)
class PackageMatch:
    package: str
    reason: str
    min_version: str = ""
    rpn: str = ""


_RULES: list = [
    (
        lambda devs: any(
            d.protocol == "feetech" and d.role == "servo-bus"
            for d in devs
        ),
        PackageMatch(
            package="so-arm101-actuator",
            reason="Feetech servo bus detected — the SO-ARM101 driver is the supported backend.",
            rpn="RPN-000000000002",
        ),
    ),
    (
        lambda devs: any(
            d.vid == "03e7" and d.pid in ("2485", "f63c") for d in devs
        ),
        PackageMatch(
            package="oak-d-actuator",
            reason="Luxonis OAK-D camera detected — installing the depth+RGB driver.",
            rpn="RPN-000000000003",
        ),
    ),
]


def match_packages_for_devices(devices: list[Device]) -> list[PackageMatch]:
    """Return the list of packages to install based on the device scan."""
    matches: list[PackageMatch] = []
    seen: set[str] = set()
    for predicate, match in _RULES:
        if predicate(devices) and match.package not in seen:
            matches.append(match)
            seen.add(match.package)
    return matches
