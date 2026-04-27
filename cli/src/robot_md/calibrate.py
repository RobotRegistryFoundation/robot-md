"""`robot-md calibrate` — populate kinematic-solver physical fields.

For any arm robot, two pieces of calibration metadata can't be inferred from
hardware autodetection alone:

1. **zero_pose_steps** per joint — the encoder reading when the joint is at
   0° in the declared kinematic convention. Set by physically posing the arm
   and reading the encoders.

2. **encoder_sign** per joint — does a positive encoder delta produce a
   positive joint-angle delta (per the convention) or a negative one? Set
   by commanding a small test move per joint and asking the operator which
   direction it went.

This module provides the non-interactive primitives. A CLI wrapper in
`__main__.py` drives the operator-facing prompts.

Scope note: tonight's v0 implements the *data pipeline* (read encoders →
rewrite the manifest with sane comment preservation) and the `--zero` mode.
The `--sign` mode and ArUco-based `--hand-eye` flag are follow-ups.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

from robot_md.parser import parse_file


def die(msg: str) -> int:
    """Print an error to stderr and return exit code 2."""
    print(f"ERROR: {msg}", file=sys.stderr)
    return 2


@dataclass
class JointReading:
    joint_id: str
    servo_id: int
    current_steps: int | None  # None if the read failed


def read_current_pose(
    manifest_path: str | Path,
    *,
    port_override: str | None = None,
    baud_override: int | None = None,
) -> list[JointReading]:
    """Connect to the arm's servo bus and read Present Position for every joint.

    Uses the port + baud + servo_id declared in the ROBOT.md. Returns one
    :class:`JointReading` per joint in `physics.kinematics[]`. Raises
    ``RuntimeError`` if the port can't be opened (gateway holding it, etc).

    Currently only supports Feetech protocol (SCServo, protocol version 0) —
    the only driver_type wired today. Extensible by adding branches keyed on
    the driver's `protocol` field.
    """
    parsed = parse_file(manifest_path)
    fm = parsed.frontmatter

    drivers = fm.get("drivers") or []
    if not drivers:
        raise RuntimeError("drivers[] empty; calibrate needs a real arm declaration")
    d = drivers[0]
    if d.get("protocol") != "feetech":
        raise RuntimeError(
            f"calibrate currently supports protocol=feetech; found {d.get('protocol')!r}. "
            "Extend robot_md/calibrate.py with a branch for your driver."
        )

    port = port_override or d.get("port") or "/dev/ttyACM0"
    baud = baud_override or int(d.get("baud_rate") or d.get("baud") or 1_000_000)

    kin = fm.get("physics", {}).get("kinematics") or []
    readings: list[JointReading] = []

    # Feetech SDK is optional at import time so tests can run without the hardware
    # dependency. Import inside the function. PyPI dist `feetech-servo-sdk`
    # ships the `scservo_sdk` Python module; the bare `PacketHandler()` factory
    # in scservo_sdk is broken upstream, so use the working `sms_sts` class
    # directly (SO-ARM101 uses the SMS/STS protocol).
    from scservo_sdk import PortHandler
    from scservo_sdk.sms_sts import sms_sts

    ADDR_PRESENT_POS = 56
    ph = PortHandler(port)
    if not ph.openPort():
        raise RuntimeError(
            f"failed to open {port} — is the OpenCastor gateway or another "
            "process holding it? Stop the gateway first."
        )
    try:
        if not ph.setBaudRate(baud):
            raise RuntimeError(f"failed to set baud {baud} on {port}")
        pk = sms_sts(ph)
        for j in kin:
            sid = j.get("servo_id")
            jid = j.get("id")
            if sid is None:
                readings.append(JointReading(jid, -1, None))
                continue
            val, comm, err = pk.read2ByteTxRx(int(sid), ADDR_PRESENT_POS)
            if comm != 0 or err != 0:
                readings.append(JointReading(jid, int(sid), None))
            else:
                readings.append(JointReading(jid, int(sid), int(val)))
    finally:
        ph.closePort()

    return readings


def write_zero_pose_to_manifest(
    manifest_path: str | Path,
    readings: list[JointReading],
) -> int:
    """Rewrite `physics.kinematics[].zero_pose_steps` for each joint where we
    have a valid reading. Preserves all comments and formatting via ruamel.yaml.

    Only touches the frontmatter block. Prose body is copied verbatim.
    Returns the number of joints updated.
    """
    try:
        from ruamel.yaml import YAML  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "`robot-md calibrate` needs ruamel.yaml for comment-preserving "
            "rewrites. Install with: pip install ruamel.yaml"
        ) from e

    path = Path(manifest_path)
    text = path.read_text()

    # Split the ROBOT.md into frontmatter + body at the "---" markers.
    if not text.startswith("---"):
        raise RuntimeError(f"{path}: missing leading '---' frontmatter marker")
    end = text.find("\n---", 3)
    if end < 0:
        raise RuntimeError(f"{path}: missing closing '---' frontmatter marker")
    fm_text = text[3:end].lstrip("\n")
    body_text = text[end + 4 :]  # includes leading newline

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    data = yaml.load(fm_text)

    kin = data.get("physics", {}).get("kinematics") or []
    by_id = {j.get("id"): j for j in kin}
    updated = 0
    for r in readings:
        if r.current_steps is None:
            continue
        j = by_id.get(r.joint_id)
        if j is None:
            continue
        j["zero_pose_steps"] = r.current_steps
        updated += 1

    import io

    buf = io.StringIO()
    yaml.dump(data, buf)
    new_text = "---\n" + buf.getvalue().rstrip("\n") + "\n---" + body_text
    path.write_text(new_text)
    return updated


def cli_calibrate_sign(manifest_path: str, *, delta_steps: int = 80) -> int:
    """Operator-facing: `robot-md calibrate --sign`.

    For each joint in `physics.kinematics[]`, command a small +delta move
    and ask the operator whether it matched the kinematic convention
    (positive rotation about the declared axis). Records `encoder_sign`
    accordingly. Always restores the original position.

    Safety: delta capped at ±150 steps (~13°). Operator can abort at any
    prompt with Ctrl-C; the arm is torqued on briefly per joint, torque
    is released afterward.
    """
    if abs(delta_steps) > 150:
        return die(f"delta_steps {delta_steps} exceeds hard cap of 150")

    parsed = parse_file(manifest_path)
    fm = parsed.frontmatter
    kin = fm.get("physics", {}).get("kinematics") or []
    drivers = fm.get("drivers") or []
    if not drivers or drivers[0].get("protocol") != "feetech":
        return die("calibrate --sign currently supports protocol=feetech only")

    port = drivers[0].get("port") or "/dev/ttyACM0"
    baud = int(drivers[0].get("baud_rate") or 1_000_000)

    from scservo_sdk import PortHandler  # lazy
    from scservo_sdk.sms_sts import sms_sts

    ADDR_TORQUE = 40
    ADDR_GOAL = 42
    ADDR_PRESENT = 56

    print(
        f"robot-md calibrate --sign — per-joint encoder direction test.\n\n"
        f"For each joint I'll command +{delta_steps} steps, wait for motion,\n"
        f"and ask whether the arm moved in the *positive* direction for that\n"
        f"joint's declared axis (per right-hand rule on the DH convention).\n"
        f"Abort any time with Ctrl-C.\n",
        file=sys.stderr,
    )

    try:
        ph = PortHandler(port)
        if not ph.openPort():
            return die(f"failed to open {port} — stop the gateway first")
        if not ph.setBaudRate(baud):
            return die(f"failed to set baud {baud}")
    except Exception as e:
        return die(f"port open failed: {e}")

    pk = sms_sts(ph)
    signs: dict[str, int] = {}
    try:
        for j in kin:
            jid = j.get("id")
            sid = j.get("servo_id")
            axis = j.get("axis", "?")
            if sid is None:
                print(f"  {jid}: no servo_id — skipping", file=sys.stderr)
                continue
            # Read start
            start, comm, err = pk.read2ByteTxRx(int(sid), ADDR_PRESENT)
            if comm != 0 or err != 0:
                print(f"  {jid}: read failed — skipping", file=sys.stderr)
                continue

            axis_hint = {
                "z": "shoulder_pan / wrist_roll: left-right rotation",
                "y": "shoulder_lift / elbow / wrist_flex: up-down rotation",
                "x": "wrist_roll: forward-backward rotation (rare)",
            }.get(axis, f"axis {axis!r}")
            print(
                f"\n→ {jid} (servo id={sid}, axis={axis}): {axis_hint}\n"
                f"  current: {start} steps, commanding +{delta_steps}...",
                file=sys.stderr,
            )

            # Torque on + command move
            pk.write1ByteTxRx(int(sid), ADDR_TORQUE, 1)
            pk.write2ByteTxRx(int(sid), ADDR_GOAL, start + delta_steps)
            time.sleep(0.9)

            try:
                ans = (
                    input(
                        "  Did the joint move in the POSITIVE convention direction? (y/n/s=skip) > "
                    )
                    .strip()
                    .lower()
                )
            except (EOFError, KeyboardInterrupt):
                print("\n  aborted — restoring position.", file=sys.stderr)
                pk.write2ByteTxRx(int(sid), ADDR_GOAL, start)
                time.sleep(0.8)
                pk.write1ByteTxRx(int(sid), ADDR_TORQUE, 0)
                return 1

            # Restore
            pk.write2ByteTxRx(int(sid), ADDR_GOAL, start)
            time.sleep(0.8)
            pk.write1ByteTxRx(int(sid), ADDR_TORQUE, 0)

            if ans.startswith("s"):
                print("  (skipped)", file=sys.stderr)
                continue
            signs[jid] = 1 if ans.startswith("y") else -1
            print(f"  ✓ encoder_sign[{jid}] = {signs[jid]:+d}", file=sys.stderr)
    finally:
        ph.closePort()

    if not signs:
        print("\nno joints calibrated.", file=sys.stderr)
        return 1

    # Rewrite manifest with the new encoder_signs
    try:
        from ruamel.yaml import YAML  # type: ignore[import-not-found]
    except ImportError:
        return die("ruamel.yaml is required — `pip install ruamel.yaml`")

    from pathlib import Path as _Path

    path = _Path(manifest_path)
    text = path.read_text()
    end = text.find("\n---", 3)
    fm_text = text[3:end].lstrip("\n")
    body_text = text[end + 4 :]
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    data = y.load(fm_text)
    for j in data.get("physics", {}).get("kinematics", []):
        if j.get("id") in signs:
            j["encoder_sign"] = signs[j["id"]]
    import io

    buf = io.StringIO()
    y.dump(data, buf)
    path.write_text("---\n" + buf.getvalue().rstrip("\n") + "\n---" + body_text)
    print(f"\n✓ wrote encoder_sign for {len(signs)} joints to {manifest_path}", file=sys.stderr)
    return 0


def cli_calibrate_zero(manifest_path: str, *, dry_run: bool = False) -> int:
    """Operator-facing entry point for `robot-md calibrate --zero`.

    Prints a prompt, reads encoder positions, and (unless `--dry-run`)
    rewrites the manifest. Returns an exit code (0 = ok).
    """
    print(
        "robot-md calibrate --zero\n\n"
        "Pose the arm in its declared ZERO configuration — i.e. every joint\n"
        "at the 0° reference of your kinematic convention (for a typical\n"
        "DH arm, that's the arm extended straight along the base +x axis,\n"
        "gripper pointing forward). When the arm is held steady, press Enter.\n",
        file=sys.stderr,
    )
    try:
        input("> ")
    except (EOFError, KeyboardInterrupt):
        print("aborted.", file=sys.stderr)
        return 1

    try:
        readings = read_current_pose(manifest_path)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print("\nCurrent encoder readings:", file=sys.stderr)
    for r in readings:
        if r.current_steps is None:
            print(f"  {r.joint_id:<16} id={r.servo_id}  → READ FAILED", file=sys.stderr)
        else:
            print(f"  {r.joint_id:<16} id={r.servo_id}  → {r.current_steps} steps", file=sys.stderr)

    if dry_run:
        print("\n--dry-run: no file changes.", file=sys.stderr)
        return 0

    try:
        n = write_zero_pose_to_manifest(manifest_path, readings)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(f"\nwrote zero_pose_steps for {n} joints to {manifest_path}", file=sys.stderr)
    return 0
