"""Bus introspection for servo chains — Tier B autodetect.

Scans a Feetech bus for responding servo IDs, reads their position +
angle limits, and returns a structured list the CLI can fold into a
draft ROBOT.md. Non-destructive: reads only. Requires the port to be
free (stop the gateway first).

Per spec/autodetect-prefill-roadmap.md §Tier B.

Supported protocols:
  * `feetech` — STS3215 / SCServo family (protocol version 0)

Dynamixel + ODrive live behind ``# TODO``s for future extension.
"""
from __future__ import annotations

import time
from dataclasses import dataclass


# STS3215 / SCServo control table addresses (in registers)
_ADDR_MIN_ANGLE_LIMIT = 0x09   # 2 bytes
_ADDR_MAX_ANGLE_LIMIT = 0x0B   # 2 bytes
_ADDR_PRESENT_POSITION = 56    # 2 bytes

# Ping range: full address space 1..253 (0 and 254..255 are reserved).
_ID_MIN = 1
_ID_MAX = 253
_PING_RETRIES = 3
_PING_BACKOFF_S = 0.020


@dataclass
class ServoEntry:
    """One responding servo's registers."""
    servo_id: int
    present_position: int | None
    min_angle_steps: int | None
    max_angle_steps: int | None

    def to_kinematics_item(self, default_id: str | None = None) -> dict:
        """Render as a preliminary kinematics[] entry.

        The joint `id` is a placeholder (`joint_<N>`) — the operator must
        rename to match the robot's actual naming convention. Servo limits
        are converted to degrees for `limits_deg`. Present position is
        written as a tentative `zero_pose_steps` candidate.
        """
        return {
            "id": default_id or f"joint_{self.servo_id}",
            "axis": "y",                      # assumed; operator verifies
            "servo_id": self.servo_id,
            "limits_deg": [
                _steps_to_deg(self.min_angle_steps) if self.min_angle_steps is not None else -180,
                _steps_to_deg(self.max_angle_steps) if self.max_angle_steps is not None else 180,
            ],
            "length_mm": 0,                   # unknown — operator fills
            "zero_pose_steps": self.present_position or 2048,
            "encoder_sign": 1,                # assumed +1; verify via calibrate --sign
        }


def _steps_to_deg(steps: int, steps_per_rev: int = 4096) -> float:
    return steps * 360.0 / steps_per_rev


def scan_feetech(port: str, baud: int = 1_000_000) -> list[ServoEntry]:
    """Scan a Feetech bus for responding servos in [1..253].

    Returns one :class:`ServoEntry` per responder. Silent IDs are skipped.
    Retries each ping up to 3 times with a 20 ms backoff to handle occasional
    transient bus collisions.
    """
    try:
        from feetech_servo_sdk import PacketHandler, PortHandler  # type: ignore[import]
    except ImportError as e:
        raise RuntimeError(
            "bus scan requires feetech_servo_sdk — install the feetech extra:\n"
            "    pip install 'robot-md[feetech]'"
        ) from e

    try:
        ph = PortHandler(port)
        opened = ph.openPort()
    except Exception as e:    # pyserial may raise SerialException on a bad port
        raise RuntimeError(
            f"failed to open {port}: {e} — is the gateway still holding the "
            "bus? Stop it first (e.g. `sudo systemctl stop castor-gateway`)."
        ) from e
    if not opened:
        raise RuntimeError(
            f"failed to open {port} — is the gateway still holding the bus? "
            "Stop it first (e.g. `sudo systemctl stop castor-gateway`)."
        )
    try:
        if not ph.setBaudRate(baud):
            raise RuntimeError(f"failed to set baud {baud} on {port}")
        pk = PacketHandler(0)  # SCServo protocol version
        found: list[ServoEntry] = []
        for sid in range(_ID_MIN, _ID_MAX + 1):
            # Ping with retries — absence of response after N tries = no servo.
            present = None
            for _ in range(_PING_RETRIES):
                val, comm, err = pk.read2ByteTxRx(ph, sid, _ADDR_PRESENT_POSITION)
                if comm == 0 and err == 0:
                    present = int(val)
                    break
                time.sleep(_PING_BACKOFF_S)
            if present is None:
                continue

            # If it responded, read limits. Failures here are soft — record None.
            lo_val, lo_comm, lo_err = pk.read2ByteTxRx(ph, sid, _ADDR_MIN_ANGLE_LIMIT)
            hi_val, hi_comm, hi_err = pk.read2ByteTxRx(ph, sid, _ADDR_MAX_ANGLE_LIMIT)
            found.append(
                ServoEntry(
                    servo_id=sid,
                    present_position=present,
                    min_angle_steps=int(lo_val) if (lo_comm == 0 and lo_err == 0) else None,
                    max_angle_steps=int(hi_val) if (hi_comm == 0 and hi_err == 0) else None,
                )
            )
        return found
    finally:
        ph.closePort()


def render_bus_scan_as_yaml(servos: list[ServoEntry]) -> str:
    """Pretty-print a scan result as a YAML `kinematics[]` block for
    pasting into a draft ROBOT.md. Output includes a header comment so
    the operator knows what to edit.
    """
    if not servos:
        return "# bus scan found no responding servos — is the bus powered?\n"
    lines: list[str] = [
        "# bus scan: "
        f"{len(servos)} servo(s) found at IDs "
        + ", ".join(str(s.servo_id) for s in servos)
        + ". Rename `joint_<N>` to match your robot's convention.",
        "physics:",
        "  kinematics:",
    ]
    for s in servos:
        it = s.to_kinematics_item()
        lines.append(
            f"    - {{ id: {it['id']}, axis: {it['axis']}, servo_id: {it['servo_id']},"
            f" limits_deg: {it['limits_deg']}, length_mm: 0,"
            f" zero_pose_steps: {it['zero_pose_steps']}, encoder_sign: {it['encoder_sign']} }}"
        )
    return "\n".join(lines) + "\n"
