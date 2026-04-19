#!/usr/bin/env python3
"""Tier 0 experiment #4 — teach-and-replay pick and place.

No calibration, no IK, no camera, no markers.

Flow:
  1. Read the arm's current pose → `start_pose`.
  2. Torque off — arm goes limp.
  3. Operator physically moves the gripper around the object. Press Enter.
     → record `pick_pose` (joints 1-5; gripper overridden to OPEN for replay).
  4. Operator physically moves the arm to the drop location. Press Enter.
     → record `place_pose`.
  5. Operator confirms clear workspace. Torque re-enabled at the
     operator's last hand position (arm holds, doesn't snap).
  6. Replay:
        start_pose          (gripper open)
        → pick_pose         (gripper still open)
        → close gripper     (grasp)
        → lift 120 steps    (shoulder_lift - 120 — ~10° raise)
        → place_pose        (carrying object, descend to drop)
        → open gripper      (release)
        → start_pose        (home)
  7. Torque off.

Motion is linearly interpolated at 30 Hz, 12 steps per tick per joint max,
so large pose changes take a few seconds instead of snapping.

    python examples/tier0/04_pick_place.py
"""
from __future__ import annotations

import sys
import time

from feetech_servo_sdk import PacketHandler, PortHandler

PORT = "/dev/ttyACM0"
BAUD = 1_000_000
JOINT_IDS = [1, 2, 3, 4, 5, 6]  # shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper
JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
GRIPPER_ID = 6
SHOULDER_LIFT_ID = 2

# Gripper positions from Bob's manifest.
GRIPPER_OPEN = 1700
GRIPPER_CLOSED = 1200

# Motion profile.
INTERP_HZ = 30
INTERP_STEPS_MAX = 12  # largest single-tick step per joint (steps); small = slow+safe
LIFT_STEPS = 120  # shoulder_lift decrement for the "up" phase (encoder_sign=1 ⇒ lower = up)

ADDR_TORQUE_ENABLE = 40
ADDR_GOAL_POSITION = 42
ADDR_PRESENT_POSITION = 56


def _write_goal(ph, port, sid, target):
    ph.write2ByteTxRx(port, sid, ADDR_GOAL_POSITION, int(target))


def _read_present(ph, port, sid):
    pos, res, err = ph.read2ByteTxRx(port, sid, ADDR_PRESENT_POSITION)
    return pos if res == 0 and err == 0 else None


def _read_pose(ph, port):
    return {sid: _read_present(ph, port, sid) for sid in JOINT_IDS}


def _set_torque(ph, port, on: bool):
    for sid in JOINT_IDS:
        ph.write1ByteTxRx(port, sid, ADDR_TORQUE_ENABLE, 1 if on else 0)


def _interpolate(ph, port, start: dict[int, int], target: dict[int, int], label: str) -> None:
    """Linearly move every joint from start→target at INTERP_HZ, bounded by INTERP_STEPS_MAX per tick."""
    # Number of ticks bounded by the largest delta / max-step-per-tick.
    deltas = {sid: target[sid] - start[sid] for sid in JOINT_IDS}
    max_delta = max(abs(d) for d in deltas.values()) if deltas else 0
    if max_delta == 0:
        return
    ticks = max(1, (max_delta + INTERP_STEPS_MAX - 1) // INTERP_STEPS_MAX)
    print(f"    interp {label}  ({ticks} ticks @ {INTERP_HZ} Hz ≈ {ticks/INTERP_HZ:.2f}s)")
    dt = 1.0 / INTERP_HZ
    for i in range(1, ticks + 1):
        alpha = i / ticks
        for sid in JOINT_IDS:
            _write_goal(ph, port, sid, int(round(start[sid] + alpha * deltas[sid])))
        time.sleep(dt)


def _fmt(pose: dict[int, int]) -> str:
    return "  ".join(f"{n}={pose.get(sid, '?'):>4}" for sid, n in zip(JOINT_IDS, JOINT_NAMES, strict=False))


def main() -> int:
    port = PortHandler(PORT)
    if not (port.openPort() and port.setBaudRate(BAUD)):
        print(f"✗ cannot open {PORT} @ {BAUD}", file=sys.stderr)
        return 1
    ph = PacketHandler(0)

    # ---------------------------------------------------------------- 1. start
    start_pose = _read_pose(ph, port)
    if any(v is None for v in start_pose.values()):
        print(f"✗ not all joints responding: {start_pose}", file=sys.stderr)
        port.closePort()
        return 1
    print(f"start_pose: {_fmt(start_pose)}")

    # ---------------------------------------------------------------- 2. teach
    print("\n▶ Releasing torque (arm goes limp). Hold it up with one hand before continuing!")
    _set_torque(ph, port, False)

    try:
        input("\n▶ Physically move the gripper around the object, fingers can stay open. Press Enter to record pick_pose > ")
    except KeyboardInterrupt:
        print("\naborted."); _set_torque(ph, port, False); port.closePort(); return 0
    pick_pose = _read_pose(ph, port)
    pick_pose[GRIPPER_ID] = GRIPPER_OPEN  # force open for the arrival phase
    print(f"pick_pose:  {_fmt(pick_pose)}")

    try:
        input("\n▶ Physically move the arm to the DROP location. Press Enter to record place_pose > ")
    except KeyboardInterrupt:
        print("\naborted."); _set_torque(ph, port, False); port.closePort(); return 0
    place_pose = _read_pose(ph, port)
    place_pose[GRIPPER_ID] = GRIPPER_CLOSED  # arrive still holding the object
    print(f"place_pose: {_fmt(place_pose)}")

    # ---------------------------------------------------------------- 3. replay
    # Where the arm physically sits right now (operator's hands-last pose).
    hand_last = _read_pose(ph, port)
    print(f"\nOperator left arm at: {_fmt(hand_last)}")

    try:
        input("\n⚠ About to enable torque AT THE CURRENT POSE, then replay. Clear the workspace. Press Enter > ")
    except KeyboardInterrupt:
        print("\naborted."); port.closePort(); return 0

    # Seed goal_position = present_position for each servo BEFORE enabling torque,
    # so the arm doesn't jerk when torque comes back on.
    for sid in JOINT_IDS:
        _write_goal(ph, port, sid, hand_last[sid])
    _set_torque(ph, port, True)
    time.sleep(0.3)

    try:
        # Build a pose for "lifted_pick" = pick_pose with shoulder_lift up.
        # encoder_sign=1 ⇒ lower value = arm up. So subtract LIFT_STEPS.
        lifted_pick = dict(pick_pose)
        lifted_pick[SHOULDER_LIFT_ID] = pick_pose[SHOULDER_LIFT_ID] - LIFT_STEPS
        lifted_pick[GRIPPER_ID] = GRIPPER_CLOSED  # holding the object

        # Also a "lifted_place" so we descend to place_pose vertically.
        lifted_place = dict(place_pose)
        lifted_place[SHOULDER_LIFT_ID] = place_pose[SHOULDER_LIFT_ID] - LIFT_STEPS
        lifted_place[GRIPPER_ID] = GRIPPER_CLOSED

        # Sequence.
        current = dict(hand_last)

        # Step A: move to pick_pose (gripper open)
        print("\n▶ A. approach pick_pose (gripper open)")
        target_a = dict(pick_pose); target_a[GRIPPER_ID] = GRIPPER_OPEN
        _interpolate(ph, port, current, target_a, "A")
        current = target_a; time.sleep(0.3)

        # Step B: close the gripper
        print("\n▶ B. close gripper (grasp)")
        target_b = dict(current); target_b[GRIPPER_ID] = GRIPPER_CLOSED
        _interpolate(ph, port, current, target_b, "B")
        current = target_b; time.sleep(0.6)  # extra settle time for grip

        # Step C: lift the object
        print(f"\n▶ C. lift {LIFT_STEPS} steps")
        _interpolate(ph, port, current, lifted_pick, "C")
        current = lifted_pick; time.sleep(0.2)

        # Step D: move to lifted_place (traverse with object raised)
        print("\n▶ D. traverse to above place_pose")
        _interpolate(ph, port, current, lifted_place, "D")
        current = lifted_place; time.sleep(0.2)

        # Step E: descend to place_pose
        print("\n▶ E. descend to place_pose")
        target_e = dict(place_pose); target_e[GRIPPER_ID] = GRIPPER_CLOSED
        _interpolate(ph, port, current, target_e, "E")
        current = target_e; time.sleep(0.3)

        # Step F: open gripper (release)
        print("\n▶ F. open gripper (release)")
        target_f = dict(current); target_f[GRIPPER_ID] = GRIPPER_OPEN
        _interpolate(ph, port, current, target_f, "F")
        current = target_f; time.sleep(0.3)

        # Step G: return home
        print("\n▶ G. return to start_pose")
        _interpolate(ph, port, current, start_pose, "G")

    finally:
        print("\nDisabling torque.")
        _set_torque(ph, port, False)
        port.closePort()

    print("\n✓ pick_place replay complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
