"""DepthAI pipeline + object detection (skeleton)."""

from __future__ import annotations

from dataclasses import dataclass

from robot_md.robot_spec import RobotSpec


@dataclass
class Perception:
    driver_id: str

    @classmethod
    def from_spec(cls, spec: RobotSpec) -> "Perception":
        cam = next(iter(spec.physics.cameras), None)
        return cls(driver_id=cam.driver_id if cam else "none")

    def close(self) -> None:
        pass

    def detect_objects(self) -> list[dict]:
        """Return [{class, bbox_xyxy, conf}]. Stubbed for now."""
        return []

    def grab_frame(self) -> bytes | None:
        return None
