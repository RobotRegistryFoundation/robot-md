"""DH kinematics + trajectory generator (skeleton)."""

from __future__ import annotations

from dataclasses import dataclass

from robot_md.robot_spec import RobotSpec


@dataclass
class Motion:
    spec: RobotSpec

    def forward(self, joint_deg: dict[str, float]) -> tuple[float, float, float]:
        """DH forward kinematics → (x, y, z) in mm. Stub zero."""
        return (0.0, 0.0, 0.0)

    def inverse(self, target_mm: tuple[float, float, float]) -> dict[str, float]:
        """DH inverse kinematics → joint-deg map. Stub zeros."""
        return {k.get("id", ""): 0.0 for k in self.spec.physics.kinematics if isinstance(k, dict)}

    def plan_trajectory(
        self, joint_deg: dict[str, float], *, max_dps: float
    ) -> list[dict]:
        """Generate a timed trajectory. Stub."""
        return [{"t": 0.0, "joints": dict(joint_deg)}]
