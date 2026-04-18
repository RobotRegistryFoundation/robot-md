"""Feetech STS3215 serial I/O wrapper (skeleton)."""

from __future__ import annotations

from dataclasses import dataclass

from robot_md.robot_spec import RobotSpec


@dataclass
class ServoBus:
    port: str
    baud: int
    count: int

    @classmethod
    def from_spec(cls, spec: RobotSpec) -> "ServoBus":
        drv = next((d for d in spec.drivers if d.protocol == "feetech"), None)
        if drv is None:
            raise RuntimeError("no feetech driver in spec")
        return cls(
            port=drv.port or "/dev/ttyACM0",
            baud=drv.baud_rate or 1_000_000,
            count=drv.count or 0,
        )

    def close(self) -> None:
        pass

    def read_positions(self) -> dict[str, int]:
        return {}

    def write_positions(self, positions: dict[str, int]) -> None:
        pass
