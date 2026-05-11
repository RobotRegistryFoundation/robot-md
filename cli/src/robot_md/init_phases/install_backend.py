"""Init phase: auto-install backend packages based on detected hardware.

Runs after `write_manifest` and before `register`. Reads the autodetect scan,
determines which backend packages (so-arm101-actuator, oak-d-actuator, …)
should be present, and pip-installs them. PEP 668 aware.

Failure on install is fatal to the init flow (the manifest references devices
the operator can't actually use without the backend).
"""

from __future__ import annotations

import os  # noqa: F401
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from robot_md.autodetect import Device
from robot_md.init_phases import PhaseResult


@dataclass(frozen=True)
class PackageMatch:
    package: str
    reason: str
    min_version: str = ""
    rpn: str = ""


_RULES: list = [
    (
        lambda devs: any(d.protocol == "feetech" and d.role == "servo-bus" for d in devs),
        PackageMatch(
            package="so-arm101-actuator",
            reason="Feetech servo bus detected — the SO-ARM101 driver is the supported backend.",
            rpn="RPN-000000000002",
        ),
    ),
    (
        lambda devs: any(
            getattr(d, "vid", None) == "03e7" and getattr(d, "pid", None) in ("2485", "f63c")
            for d in devs
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


def is_externally_managed_env() -> bool:
    """True when the current Python install is PEP-668 externally-managed.

    - In a venv (sys.prefix != sys.base_prefix) → False (never managed).
    - Otherwise, look for an `EXTERNALLY-MANAGED` marker in the stdlib dir.
      Pi OS Bookworm+ ships one; pure Python.org installs do not.
    """
    import sysconfig

    if sys.prefix != sys.base_prefix:
        return False
    stdlib = Path(sysconfig.get_path("stdlib"))
    marker = stdlib / "EXTERNALLY-MANAGED"
    return marker.exists()


@dataclass(frozen=True)
class InstallResult:
    package: str
    ok: bool
    stdout: str = ""
    stderr: str = ""


def install_one(package: str, *, min_version: str = "") -> InstallResult:
    """Run `pip install --user [--break-system-packages] <pkg>[>=ver]`.

    Emits a one-line stderr explanation when --break-system-packages is added
    so the operator can see the workaround without surprise.
    """
    spec = package + (f">={min_version}" if min_version else "")
    cmd = [sys.executable, "-m", "pip", "install", "--user", spec]
    if is_externally_managed_env():
        cmd.insert(cmd.index("install") + 1, "--break-system-packages")
        sys.stderr.write(
            "⚠ Adding --break-system-packages because this Python install is "
            "externally-managed (PEP 668). Consider pipx for a cleaner future install.\n"
        )
    result = subprocess.run(cmd, capture_output=True, text=True)
    return InstallResult(
        package=package,
        ok=(result.returncode == 0),
        stdout=result.stdout,
        stderr=result.stderr,
    )


def phase_install_backend(scan) -> PhaseResult:
    """Init phase entry point. Installs all backend packages indicated by the scan."""
    matches = match_packages_for_devices(scan.devices)
    if not matches:
        return PhaseResult(
            phase="install_backend",
            status="ok",
            message="no backend packages required (no matching hardware)",
            detail={"installed": []},
        )
    installed: list[str] = []
    for m in matches:
        sys.stdout.write(f"  • {m.reason}\n")
        sys.stdout.write(f"    Installing {m.package}…\n")
        r = install_one(m.package, min_version=m.min_version)
        if not r.ok:
            stderr_tail = r.stderr.splitlines()[-1] if r.stderr else "unknown error"
            return PhaseResult(
                phase="install_backend",
                status="failed",
                message=f"failed to install {r.package}: {stderr_tail}",
                detail={
                    "installed": installed,
                    "failed_package": r.package,
                    "stderr": r.stderr,
                },
            )
        installed.append(r.package)
        sys.stdout.write(f"    ✓ {r.package}\n")
    return PhaseResult(
        phase="install_backend",
        status="ok",
        message=f"installed {len(installed)} backend package(s)",
        detail={"installed": installed},
    )
