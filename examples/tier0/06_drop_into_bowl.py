#!/usr/bin/env python3
"""Tier 0 experiment #6 — drop the currently-held Lego into the bowl.

Continuation of experiment #4. Assumes the gripper is ALREADY closed
around a small object (Lego, block, etc.) and the operator wants to
place it at a target location (e.g., into a bowl).

Flow:
  1. Read current pose → `hold_pose` (arm currently holding the object).
  2. Prompt: "I'll capture an RGB snapshot for the record." → saves /tmp/tier0/drop_before.jpg.
  3. Torque off. Arm goes limp.
  4. Operator physically moves the arm so the gripper is DIRECTLY ABOVE
     the bowl at the height you want the release to happen. Enter.
     → record `drop_pose`.
  5. Torque re-enabled at operator's hands-last pose.
  6. Replay:
        current → drop_pose  (smooth interpolation, gripper stays CLOSED)
        → open gripper       (release — object falls)
        → back to hold_pose  (arm returns, empty gripper)
  7. Torque off.
  8. Snap again → /tmp/tier0/drop_after.jpg so we can compare.

    python examples/tier0/06_drop_into_bowl.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from feetech_servo_sdk import PacketHandler, PortHandler

PORT = "/dev/ttyACM0"
BAUD = 1_000_000
JOINT_IDS = [1, 2, 3, 4, 5, 6]
JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
GRIPPER_ID = 6

GRIPPER_OPEN = 1700
# Gripper stays closed during transit — we snapshot whatever the operator has
# physically clamped it to in the hold phase and hold that exact value.

INTERP_HZ = 30
INTERP_STEPS_MAX = 10  # slightly slower than exp #4 — we're carrying something

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


def _interpolate(ph, port, start, target, label):
    deltas = {sid: target[sid] - start[sid] for sid in JOINT_IDS}
    max_delta = max(abs(d) for d in deltas.values()) if deltas else 0
    if max_delta == 0:
        return
    ticks = max(1, (max_delta + INTERP_STEPS_MAX - 1) // INTERP_STEPS_MAX)
    print(f"    interp {label} ({ticks} ticks @ {INTERP_HZ} Hz ≈ {ticks/INTERP_HZ:.2f}s)")
    dt = 1.0 / INTERP_HZ
    for i in range(1, ticks + 1):
        alpha = i / ticks
        for sid in JOINT_IDS:
            _write_goal(ph, port, sid, int(round(start[sid] + alpha * deltas[sid])))
        time.sleep(dt)


def _fmt(pose):
    return "  ".join(f"{n}={pose.get(sid, '?'):>4}" for sid, n in zip(JOINT_IDS, JOINT_NAMES, strict=False))


def _snapshot(save_to: str) -> None:
    """Best-effort RGB snapshot. Silently skips if depthai not available or busy."""
    try:
        import cv2
        import depthai as dai
    except ImportError:
        print(f"    (camera snapshot skipped — depthai/cv2 not available)")
        return

    try:
        with dai.Pipeline() as pipe:
            cam = pipe.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
            out = cam.requestOutput(size=(1280, 720), type=dai.ImgFrame.Type.NV12)
            q = out.createOutputQueue()
            pipe.start()
            frame = None
            for _ in range(15):  # warmup
                msg = q.get()
                if msg is not None:
                    frame = msg.getCvFrame()
            if frame is not None:
                Path(save_to).parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(save_to, frame)
                print(f"    📷 saved {save_to}")
    except Exception as exc:
        print(f"    (snapshot failed: {exc})")


def main() -> int:
    port = PortHandler(PORT)
    if not (port.openPort() and port.setBaudRate(BAUD)):
        print(f"✗ cannot open {PORT} @ {BAUD}", file=sys.stderr)
        return 1
    ph = PacketHandler(0)

    hold_pose = _read_pose(ph, port)
    if any(v is None for v in hold_pose.values()):
        print(f"✗ not all joints responding: {hold_pose}", file=sys.stderr)
        port.closePort()
        return 1
    print(f"hold_pose (arm currently): {_fmt(hold_pose)}")
    print(f"  gripper currently at: {hold_pose[GRIPPER_ID]} (will be preserved through transit)")

    print("\n📷 Taking BEFORE snapshot…")
    _snapshot("/tmp/tier0/drop_before.jpg")

    print("\n▶ Releasing torque — HOLD THE ARM with one hand before continuing.")
    _set_torque(ph, port, False)

    try:
        input("\n▶ Physically move the gripper DIRECTLY ABOVE the bowl at release height. Press Enter > ")
    except KeyboardInterrupt:
        print("\naborted — re-enabling torque is up to you.")
        port.closePort()
        return 0

    drop_pose = _read_pose(ph, port)
    # Preserve whatever gripper value the operator's hand might have bumped.
    drop_pose[GRIPPER_ID] = hold_pose[GRIPPER_ID]
    print(f"drop_pose: {_fmt(drop_pose)}")

    hand_last = _read_pose(ph, port)  # operator may have released the arm; read fresh

    try:
        input("\n⚠ About to re-enable torque at current pose + replay. Clear the workspace. Press Enter > ")
    except KeyboardInterrupt:
        print("\naborted."); port.closePort(); return 0

    # Seed goals = present before torque on → no snap.
    for sid in JOINT_IDS:
        _write_goal(ph, port, sid, hand_last[sid])
    _set_torque(ph, port, True)
    time.sleep(0.3)

    try:
        # Step A: move from current pose to drop_pose, gripper stays closed
        print("\n▶ A. traverse to drop_pose (gripper stays closed, carrying object)")
        _interpolate(ph, port, hand_last, drop_pose, "A")
        time.sleep(0.5)

        # Step B: open gripper → release object into bowl
        print("\n▶ B. open gripper — RELEASE")
        release_pose = dict(drop_pose); release_pose[GRIPPER_ID] = GRIPPER_OPEN
        _interpolate(ph, port, drop_pose, release_pose, "B")
        time.sleep(0.8)  # let the object fall

        # Step C: return home (hold_pose but with gripper open)
        print("\n▶ C. retract to starting pose (empty gripper)")
        retract_pose = dict(hold_pose); retract_pose[GRIPPER_ID] = GRIPPER_OPEN
        _interpolate(ph, port, release_pose, retract_pose, "C")

    finally:
        print("\nDisabling torque.")
        _set_torque(ph, port, False)
        port.closePort()

    print("\n📷 Taking AFTER snapshot…")
    _snapshot("/tmp/tier0/drop_after.jpg")

    print("\n✓ drop-into-bowl complete. Compare:")
    print("  /tmp/tier0/drop_before.jpg  (arm holding Lego)")
    print("  /tmp/tier0/drop_after.jpg   (Lego should be in the bowl, arm retracted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
