#!/usr/bin/env python3
"""Tier 0 experiment #2 — wiggle the gripper only. Safest possible first motion.

Moves just servo 6 (gripper) by ±100 steps from its current position and
back. No arm motion. If this works, the full actuation loop (torque
enable → goal position → disable) is verified.

    python examples/tier0/02_gripper_wiggle.py
"""
from __future__ import annotations

import sys
import time

from feetech_servo_sdk import PacketHandler, PortHandler

PORT = "/dev/ttyACM0"
BAUD = 1_000_000

# Gripper is servo 6 per the SO-ARM101 preset in the ROBOT.md manifest.
GRIPPER_ID = 6

# Motion size — small enough that even if wrong direction, nothing bad happens.
DELTA = 100

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
    start = _read_pos(ph, port, GRIPPER_ID)
    if start is None:
        print(f"✗ gripper (servo {GRIPPER_ID}) not responding", file=sys.stderr)
        port.closePort()
        return 1

    print(f"Gripper starting position: {start}")
    print(f"Plan: close by {DELTA} → hold 1s → open by {DELTA} → hold 1s → back to start.")

    try:
        input("\n⚠ about to enable gripper torque. Press Enter to proceed (Ctrl+C to abort) > ")
    except KeyboardInterrupt:
        print("\naborted.")
        port.closePort()
        return 0

    # Enable torque on JUST the gripper.
    ph.write1ByteTxRx(port, GRIPPER_ID, ADDR_TORQUE_ENABLE, 1)

    try:
        target_close = start - DELTA
        target_open = start + DELTA

        print(f"\n▶ close  → target {target_close}")
        _write_pos(ph, port, GRIPPER_ID, target_close)
        time.sleep(1.0)
        print(f"  present: {_read_pos(ph, port, GRIPPER_ID)}")

        print(f"\n▶ open   → target {target_open}")
        _write_pos(ph, port, GRIPPER_ID, target_open)
        time.sleep(1.0)
        print(f"  present: {_read_pos(ph, port, GRIPPER_ID)}")

        print(f"\n▶ return → target {start}")
        _write_pos(ph, port, GRIPPER_ID, start)
        time.sleep(1.0)
        print(f"  present: {_read_pos(ph, port, GRIPPER_ID)}")

    finally:
        # Always disable torque on exit, even on Ctrl+C.
        print("\nDisabling gripper torque (goes limp).")
        ph.write1ByteTxRx(port, GRIPPER_ID, ADDR_TORQUE_ENABLE, 0)
        port.closePort()

    print("\n✓ gripper wiggle complete. If you saw the gripper move (close → open → return), the actuation loop works.")
    print("  Next: experiment #3 will move a single arm joint (shoulder_pan) by the same tiny delta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
