#!/usr/bin/env python3
"""Tier 0 experiment #3 — wiggle shoulder_pan (base rotation) ±100 steps.

First ARM motion. Rotates the entire arm around the vertical base axis by
roughly ±9° (100 / 4096 × 360°). Because this rotates everything above the
base, the end-effector will sweep through a wider arc than 9° — make sure
nothing's in the path.

    python examples/tier0/03_shoulder_pan_wiggle.py
"""
from __future__ import annotations

import sys
import time

from feetech_servo_sdk import PacketHandler, PortHandler

PORT = "/dev/ttyACM0"
BAUD = 1_000_000

# shoulder_pan is servo 1 per the SO-ARM101 preset.
JOINT_ID = 1
JOINT_NAME = "shoulder_pan"
DELTA = 100  # ≈ 9° — small on paper, but the end-effector arcs further.

ADDR_TORQUE_ENABLE = 40
ADDR_GOAL_POSITION = 42
ADDR_PRESENT_POSITION = 56


def _write_pos(ph, port, sid: int, target: int) -> bool:
    res, err = ph.write2ByteTxRx(port, sid, ADDR_GOAL_POSITION, int(target))
    if res != 0 or err != 0:
        print(f"  ✗ write goal_pos to servo {sid}: res={res} err={err}", file=sys.stderr)
        return False
    return True


def _read_pos(ph, port, sid: int) -> int | None:
    pos, res, err = ph.read2ByteTxRx(port, sid, ADDR_PRESENT_POSITION)
    return pos if res == 0 and err == 0 else None


def main() -> int:
    port = PortHandler(PORT)
    if not (port.openPort() and port.setBaudRate(BAUD)):
        print(f"✗ cannot open {PORT} @ {BAUD}", file=sys.stderr)
        return 1

    ph = PacketHandler(0)
    start = _read_pos(ph, port, JOINT_ID)
    if start is None:
        print(f"✗ {JOINT_NAME} (servo {JOINT_ID}) not responding", file=sys.stderr)
        port.closePort()
        return 1

    print(f"{JOINT_NAME} (servo {JOINT_ID}) starting position: {start}")
    print(f"Plan: -{DELTA} → hold 1.5s → +{DELTA} → hold 1.5s → back to {start}.")
    print("⚠ The whole arm rotates around the base. Make sure nothing's in the sweep path.")

    try:
        input("\nPress Enter to enable torque and begin (Ctrl+C to abort) > ")
    except KeyboardInterrupt:
        print("\naborted.")
        port.closePort()
        return 0

    ph.write1ByteTxRx(port, JOINT_ID, ADDR_TORQUE_ENABLE, 1)

    try:
        for label, target in (
            (f"-{DELTA}", start - DELTA),
            (f"+{DELTA}", start + DELTA),
            ("return", start),
        ):
            print(f"\n▶ {label:<8} → target {target}")
            _write_pos(ph, port, JOINT_ID, target)
            time.sleep(1.5)
            present = _read_pos(ph, port, JOINT_ID)
            err = abs(present - target) if present is not None else "?"
            print(f"  present: {present}  (error: {err} steps)")
    finally:
        print("\nDisabling torque.")
        ph.write1ByteTxRx(port, JOINT_ID, ADDR_TORQUE_ENABLE, 0)
        port.closePort()

    print(f"\n✓ {JOINT_NAME} wiggle complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
