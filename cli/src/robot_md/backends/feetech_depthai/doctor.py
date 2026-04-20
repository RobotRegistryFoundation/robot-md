"""Hardware-state doctor checks for the feetech + depthai backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Check:
    name: str
    status: str  # "pass" | "warn" | "error" | "info"
    message: str


def hw_checks(
    *,
    bus: Any,
    camera: Any,
    expected_servo_ids: set[str],
) -> list[Check]:
    """Enumerate the bus, probe the camera, return a flat list of Checks."""
    checks: list[Check] = []

    # Servo enumeration.
    try:
        observed = set((bus.read_positions() or {}).keys())
    except Exception as e:
        checks.append(Check("servo_enumeration", "error", f"bus read failed: {e}"))
    else:
        missing = expected_servo_ids - observed
        extra = observed - expected_servo_ids
        if not missing and not extra:
            checks.append(Check("servo_enumeration", "pass", f"all {len(observed)} servos present"))
        elif missing:
            checks.append(
                Check(
                    "servo_enumeration",
                    "warn",
                    f"missing servo ids {sorted(missing)}; possible latch — power-cycle bus",
                )
            )
        else:
            checks.append(Check("servo_enumeration", "info", f"extra servo ids {sorted(extra)}"))

    # Camera streams.
    try:
        probe = camera.probe() or {}
    except Exception as e:
        probe = {}
        checks.append(Check("camera_probe", "error", f"camera probe failed: {e}"))

    checks.append(
        Check(
            "rgb_stream",
            "pass" if probe.get("rgb") else "error",
            "rgb stream present" if probe.get("rgb") else "rgb stream unavailable",
        )
    )
    checks.append(
        Check(
            "depth_stream",
            "pass" if probe.get("depth") else "error",
            "depth stream present" if probe.get("depth") else (
                "depth stream unavailable; depth-aware detectors will fail"
            ),
        )
    )
    return checks
