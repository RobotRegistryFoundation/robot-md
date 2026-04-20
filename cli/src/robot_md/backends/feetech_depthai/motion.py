"""Trajectory replay + (future-P4) pose-adjust and forward kinematics.

Phase 1 scope: `replay(waypoints, servo_bus, estop)` — iterates consecutive
waypoint pairs and calls servo_bus.interpolate between them. Single-waypoint
trajectories are treated as one-shot position commands.

Forward kinematics and pose-adjust are Phase 4 (hand-eye).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from robot_md.backends.feetech_depthai.servo import ServoBus
from robot_md.robot_spec import RobotSpec


@dataclass
class AliveReport:
    """Post-motion servo enumeration result.

    alive:    True iff every expected servo responded on the bus.
    missing:  servo ids that did not respond (sorted for stable output).
    """

    alive: bool
    missing: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Waypoint:
    t: float
    joints: dict[str, int]


@dataclass
class Motion:
    spec: RobotSpec

    @classmethod
    def from_spec(cls, spec: RobotSpec) -> Motion:
        return cls(spec=spec)

    def replay(
        self,
        waypoints: list[Waypoint],
        *,
        servo_bus: ServoBus,
        estop,
        hz: int = 30,
        max_steps_per_tick: int = 12,
    ) -> None:
        """Drive `servo_bus` through consecutive waypoint pairs."""
        if not waypoints:
            return
        if len(waypoints) == 1:
            # Interpolate from current position to the single target so servos
            # actually reach it before the caller torques off. A plain goal
            # write returns immediately; STS3215 at default speed can take
            # ~1s to cross a large delta.
            start = servo_bus.read_positions()
            if start:
                servo_bus.interpolate(
                    start,
                    waypoints[0].joints,
                    hz=hz,
                    max_steps_per_tick=max_steps_per_tick,
                    estop=estop,
                )
            else:
                servo_bus.write_positions(waypoints[0].joints)
            return
        for i in range(len(waypoints) - 1):
            if estop.is_set():
                return
            start = waypoints[i].joints
            target = waypoints[i + 1].joints
            servo_bus.interpolate(
                start,
                target,
                hz=hz,
                max_steps_per_tick=max_steps_per_tick,
                estop=estop,
            )

    def verify_alive(self, servo_bus, *, expected_ids: set[str]) -> AliveReport:
        """Read bus enumeration; if any expected servo is missing, torque off
        the remaining (safety) and return an AliveReport that the caller can
        turn into a structured error.

        Called after every motion by the dispatch layer. The single observed
        failure mode in hardware is that a latched STS3215 drops from the bus
        enumeration entirely (no error response) — we detect by set difference.
        """
        try:
            observed = set(servo_bus.read_positions().keys())
        except Exception:
            # Bus-level failure is different from latch — surface as all-missing.
            servo_bus.torque(False)
            return AliveReport(alive=False, missing=sorted(expected_ids))

        missing = sorted(expected_ids - observed)
        if missing:
            servo_bus.torque(False)
            return AliveReport(alive=False, missing=missing)
        return AliveReport(alive=True, missing=[])
