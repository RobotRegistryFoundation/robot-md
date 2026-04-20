"""Trajectory replay + (future-P4) pose-adjust and forward kinematics.

Phase 1 scope: `replay(waypoints, servo_bus, estop)` — iterates consecutive
waypoint pairs and calls servo_bus.interpolate between them. Single-waypoint
trajectories are treated as one-shot position commands.

Forward kinematics and pose-adjust are Phase 4 (hand-eye).
"""

from __future__ import annotations

from dataclasses import dataclass

from robot_md.backends.feetech_depthai.servo import ServoBus
from robot_md.robot_spec import RobotSpec


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
