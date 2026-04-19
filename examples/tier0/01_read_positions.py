#!/usr/bin/env python3
"""Tier 0 experiment #1 — read the current joint positions. No motion.

Run this first. If it prints six positions in the 0-4096 range and no
errors, the bus is alive and we can safely run experiment #2.

    python examples/tier0/01_read_positions.py
"""
from __future__ import annotations

import sys

from feetech_servo_sdk import PacketHandler, PortHandler

PORT = "/dev/ttyACM0"
BAUD = 1_000_000
SERVO_IDS = [1, 2, 3, 4, 5, 6]
JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]

ADDR_PRESENT_POSITION = 56
ADDR_PRESENT_VOLTAGE = 62  # 1 byte, voltage × 10


def main() -> int:
    port = PortHandler(PORT)
    if not port.openPort():
        print(f"✗ cannot open {PORT}", file=sys.stderr)
        return 1
    if not port.setBaudRate(BAUD):
        print(f"✗ cannot set baud {BAUD}", file=sys.stderr)
        port.closePort()
        return 1

    ph = PacketHandler(0)  # STS3215 uses protocol 0

    print(f"Connected to {PORT} @ {BAUD} baud. Reading 6 servos:\n")
    print(f"  {'ID':<4}{'joint':<16}{'position':<12}{'voltage':<10}{'status'}")
    print(f"  {'-' * 60}")

    ok_count = 0
    for sid, name in zip(SERVO_IDS, JOINT_NAMES, strict=False):
        pos, res, err = ph.read2ByteTxRx(port, sid, ADDR_PRESENT_POSITION)
        volts_raw, vres, verr = ph.read1ByteTxRx(port, sid, ADDR_PRESENT_VOLTAGE)

        if res != 0 or err != 0:
            print(f"  {sid:<4}{name:<16}{'—':<12}{'—':<10}[red]✗ {res}/{err}")
            continue

        volts_str = f"{volts_raw / 10:.1f} V" if vres == 0 and verr == 0 else "?"
        print(f"  {sid:<4}{name:<16}{pos:<12}{volts_str:<10}✓")
        ok_count += 1

    port.closePort()

    print(f"\n{ok_count}/6 servos responding.")
    if ok_count == 6:
        print("✓ bus is alive. Safe to run experiment #2 (tiny wiggle).")
        return 0
    print("⚠ not all servos responding. Check power + cables before moving on.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
