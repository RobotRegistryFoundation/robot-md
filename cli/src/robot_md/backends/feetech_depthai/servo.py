"""Feetech STS3215 serial I/O wrapper.

Ports the working wire-protocol usage from `examples/tier0/01_read_positions.py`,
`examples/tier0/02_gripper_wiggle.py`, `examples/tier0/03_shoulder_pan_wiggle.py`,
and the `_interpolate` helper from `examples/tier0/04_pick_place.py`.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field

from robot_md.robot_spec import RobotSpec

# STS3215 register addresses (from tier0 examples)
ADDR_TORQUE_ENABLE = 40
ADDR_GOAL_POSITION = 42
ADDR_PRESENT_POSITION = 56

# Canonical servo_id → joint_name mapping for SO-ARM101.
_DEFAULT_JOINT_IDS: tuple[int, ...] = (1, 2, 3, 4, 5, 6)
_DEFAULT_JOINT_NAMES: tuple[str, ...] = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)


@dataclass
class ServoBus:
    port: str
    baud: int
    count: int
    joint_ids: tuple[int, ...] = field(default=_DEFAULT_JOINT_IDS)
    joint_names: tuple[str, ...] = field(default=_DEFAULT_JOINT_NAMES)

    _port: object | None = None
    _ph: object | None = None

    @classmethod
    def from_spec(cls, spec: RobotSpec) -> ServoBus:
        drv = next((d for d in spec.drivers if d.protocol == "feetech"), None)
        if drv is None:
            raise RuntimeError("no feetech driver in spec")
        return cls(
            port=drv.port or "/dev/ttyACM0",
            baud=drv.baud_rate or 1_000_000,
            count=drv.count or len(_DEFAULT_JOINT_IDS),
        )

    def open(self) -> None:
        from scservo_sdk import PortHandler
        from scservo_sdk.sms_sts import sms_sts

        p = PortHandler(self.port)
        if not p.openPort():
            raise RuntimeError(f"cannot open {self.port}")
        if not p.setBaudRate(self.baud):
            p.closePort()
            raise RuntimeError(f"cannot set baud {self.baud} on {self.port}")
        self._port = p
        self._ph = sms_sts(p)

    def close(self) -> None:
        if self._port is not None:
            with contextlib.suppress(Exception):
                self._port.closePort()
        self._port = None
        self._ph = None

    # ------------------------------------------------------------------ reads

    def read_positions(self) -> dict[str, int]:
        """Return {joint_name: steps} for every servo that responds.

        Non-responders (result != 0 or error != 0) are silently omitted.
        Returns empty dict if bus is not open.
        """
        if self._ph is None or self._port is None:
            return {}
        out: dict[str, int] = {}
        for sid, name in zip(self.joint_ids, self.joint_names, strict=True):
            pos, result, err = self._ph.read2ByteTxRx(sid, ADDR_PRESENT_POSITION)
            if result == 0 and err == 0:
                out[name] = int(pos)
        return out

    # ----------------------------------------------------------------- writes

    def write_positions(self, positions: dict[str, int]) -> None:
        """Send a one-shot goal-position write for each named joint present."""
        if self._ph is None or self._port is None:
            raise RuntimeError("ServoBus not open")
        name_to_id = dict(zip(self.joint_names, self.joint_ids, strict=True))
        for name, target in positions.items():
            sid = name_to_id.get(name)
            if sid is None:
                continue
            self._ph.write2ByteTxRx(sid, ADDR_GOAL_POSITION, int(target))

    def torque(self, on: bool) -> None:
        """Enable/disable torque on every joint."""
        if self._ph is None or self._port is None:
            raise RuntimeError("ServoBus not open")
        val = 1 if on else 0
        for sid in self.joint_ids:
            self._ph.write1ByteTxRx(sid, ADDR_TORQUE_ENABLE, val)

    # ----------------------------------------------------------- interpolate

    def interpolate(
        self,
        start: dict[str, int],
        target: dict[str, int],
        *,
        hz: int = 30,
        max_steps_per_tick: int = 12,
        estop,
    ) -> None:
        """Linearly drive joints from start → target at `hz`, bounded per-tick.

        Ported from `examples/tier0/04_pick_place.py::_interpolate`. Checks
        `estop.is_set()` before each tick; returns early if set.
        """
        if self._ph is None or self._port is None:
            raise RuntimeError("ServoBus not open")
        name_to_id = dict(zip(self.joint_names, self.joint_ids, strict=True))
        deltas: dict[str, int] = {n: target[n] - start[n] for n in start if n in target}
        max_delta = max((abs(d) for d in deltas.values()), default=0)
        if max_delta == 0:
            return
        ticks = max(1, (max_delta + max_steps_per_tick - 1) // max_steps_per_tick)
        dt = 1.0 / hz
        for i in range(1, ticks + 1):
            if estop is not None and estop.is_set():
                return
            alpha = i / ticks
            for n, d in deltas.items():
                sid = name_to_id.get(n)
                if sid is None:
                    continue
                val = round(start[n] + alpha * d)
                self._ph.write2ByteTxRx(sid, ADDR_GOAL_POSITION, val)
            time.sleep(dt)
