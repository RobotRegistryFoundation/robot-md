"""Hand-eye calibration — solve the OAK-D ↔ arm-base extrinsic via AX = XB.

The operator prints a planar ArUco tag of known size (default 50 mm) and
places it somewhere the camera can see. They run::

    robot-md calibrate --hand-eye ROBOT.md --marker-pos 300,0,0 --marker-size 50

The CLI drives an 8-pose sweep via the live backend:

1. At each pose, moves the arm to a perturbation of ``physics.poses.ready``.
2. Grabs an RGB frame + intrinsics from the OAK-D and detects the ArUco
   marker, recording (R_target2cam, t_target2cam).
3. Records the current forward-kinematic end-effector pose as
   (R_gripper2base, t_gripper2base).
4. After >=3 good samples, calls ``cv2.calibrateHandEye`` (AX = XB, Tsai)
   to recover the camera-in-arm-base transform.
5. Writes the 6-vector ``[tx, ty, tz, rx, ry, rz]`` to
   ``physics.solver.cameras[0].extrinsic`` and flips ``extrinsic_source``
   to ``hand_eye_calibrated``.

The old v0.5.0 single-shot PnP path has been replaced — the AX = XB sweep
is more robust (averages over samples) and doesn't require the operator
to know the marker's exact arm-base coordinates. ``marker_pos`` is kept
informational for operator feedback.

Dependencies: opencv-contrib-python (provides cv2.aruco), numpy.
All optional — the ``vision`` extras install them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np


def write_extrinsic(manifest_path, *, six_vec, source: str) -> None:
    """In-place update: set ``physics.solver.cameras[0].extrinsic`` + source.

    ``six_vec`` is a 6-tuple of floats ``(tx, ty, tz, rx, ry, rz)`` in mm
    and radians; ``source`` is written verbatim to ``extrinsic_source``.
    """
    import yaml

    path = Path(manifest_path)
    text = path.read_text()
    if not text.startswith("---\n"):
        raise RuntimeError("manifest missing YAML frontmatter")
    _, rest = text.split("---\n", 1)
    yaml_part, _, body = rest.partition("\n---\n")
    fm = yaml.safe_load(yaml_part) or {}
    cams = fm.setdefault("physics", {}).setdefault("solver", {}).setdefault("cameras", [])
    if not cams:
        cams.append({"driver_id": "oakd", "primary_stream": "rgb", "mount": "world"})
    cams[0]["extrinsic"] = [float(v) for v in six_vec]
    cams[0]["extrinsic_source"] = source
    tail = "\n---\n" + body if body else "\n---\n"
    path.write_text("---\n" + yaml.safe_dump(fm, sort_keys=False) + tail)


def calibrate_from_samples(
    *,
    R_gripper2base: Sequence[np.ndarray],
    t_gripper2base: Sequence[np.ndarray],
    R_target2cam: Sequence[np.ndarray],
    t_target2cam: Sequence[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """Wrap cv2.calibrateHandEye. Returns (R_cam2base, t_cam2base)."""
    import cv2

    n = len(R_gripper2base)
    if n < 3:
        raise ValueError(f"hand-eye needs at least 3 samples, got {n}")
    if not (n == len(t_gripper2base) == len(R_target2cam) == len(t_target2cam)):
        raise ValueError("all four sample lists must be the same length")

    R, t = cv2.calibrateHandEye(
        R_gripper2base=list(R_gripper2base),
        t_gripper2base=list(t_gripper2base),
        R_target2cam=list(R_target2cam),
        t_target2cam=list(t_target2cam),
        method=cv2.CALIB_HAND_EYE_TSAI,
    )
    t = np.asarray(t).reshape(-1)
    return (np.asarray(R), t)


def detect_marker_pose(
    frame,
    *,
    K: np.ndarray,
    dist_coeffs: np.ndarray,
    marker_id: int,
    marker_size_mm: float,
    dictionary_id: int | None = None,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Find a single ArUco marker in an RGB frame. Returns (R, t) in cam frame, mm."""
    import cv2

    dict_id = dictionary_id if dictionary_id is not None else cv2.aruco.DICT_4X4_50
    dictionary = cv2.aruco.getPredefinedDictionary(dict_id)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, params)
    corners, ids, _ = detector.detectMarkers(frame)
    if ids is None or len(ids) == 0:
        return None
    matches = [i for i, row in enumerate(ids) if int(row[0]) == marker_id]
    if not matches:
        return None
    idx = matches[0]
    rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
        [corners[idx]], marker_size_mm, K, dist_coeffs
    )
    R, _ = cv2.Rodrigues(rvecs[0][0])
    t = tvecs[0][0]
    return (R, t)


def _run_sweep(
    manifest_path,
    *,
    marker_pos,
    marker_size_mm: float,
    marker_id: int,
):
    """Drive the 8-pose sweep. Returns (R_cam2base, t_cam2base).

    Hardware path. Opens the feetech bus + OAK-D via the live backend.
    Gated out in tests by patching this function.
    """
    import time

    from robot_md.kinematics import Kinematics
    from robot_md.mcp.context import load_context
    from robot_md.parser import parse_file

    path = Path(manifest_path)
    parsed = parse_file(path).frontmatter
    kin = Kinematics(parsed)
    ready = (parsed.get("physics") or {}).get("poses", {}).get("ready", {}).get("joints")
    if ready is None:
        raise RuntimeError("physics.poses.ready missing — run init first")

    ctx = load_context(path)
    backend = ctx.backend
    if backend is None or backend._servo_bus is None or backend._perception is None:
        raise RuntimeError("feetech bus or perception unavailable")

    deltas = [
        {}, {"shoulder_pan": 100}, {"shoulder_pan": -100},
        {"shoulder_lift": 80}, {"shoulder_lift": -80},
        {"elbow_flex": 80}, {"wrist_flex": 80}, {"wrist_roll": 100},
    ]

    R_gb, t_gb, R_tc, t_tc = [], [], [], []
    backend._servo_bus.torque(True)
    try:
        for d in deltas:
            target = {**ready, **{k: ready[k] + v for k, v in d.items() if k in ready}}
            backend._motion.move_to_joints(target, servo_bus=backend._servo_bus)
            time.sleep(0.5)
            rgb, _depth, K = backend._perception.grab_frame()
            pose = detect_marker_pose(
                rgb,
                K=np.asarray(K),
                dist_coeffs=np.zeros(5),
                marker_id=marker_id,
                marker_size_mm=marker_size_mm,
            )
            if pose is None:
                continue
            R_target_cam, t_target_cam = pose
            angles = kin.steps_to_angles(target)
            x, y, z = kin.fk(angles)
            R_gb.append(np.eye(3))
            t_gb.append(np.array([x, y, z], dtype=float))
            R_tc.append(R_target_cam)
            t_tc.append(t_target_cam)
    finally:
        backend._servo_bus.torque(False)

    if len(R_gb) < 3:
        raise RuntimeError(f"insufficient marker detections ({len(R_gb)} < 3)")
    _ = marker_pos  # reserved for future known-marker solver
    return calibrate_from_samples(
        R_gripper2base=R_gb,
        t_gripper2base=t_gb,
        R_target2cam=R_tc,
        t_target2cam=t_tc,
    )


def cli_calibrate_hand_eye(
    manifest_path: str,
    *,
    marker_pos,
    marker_size_mm: float = 50.0,
    marker_id: int = 0,
    dry_run: bool = False,
) -> int:
    """CLI entry: drive AX=XB sweep, write extrinsic, flip source."""
    from robot_md.extrinsic import matrix_to_six_vec

    mpath = Path(manifest_path)
    print(
        f"hand-eye: marker id={marker_id} size={marker_size_mm:.0f}mm "
        f"at arm-base ({marker_pos[0]:.0f}, {marker_pos[1]:.0f}, {marker_pos[2]:.0f}) mm"
    )
    try:
        R, t = _run_sweep(
            mpath,
            marker_pos=marker_pos,
            marker_size_mm=marker_size_mm,
            marker_id=marker_id,
        )
    except Exception as e:
        print(f"hand-eye failed: {e}")
        return 1
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = np.asarray(t).reshape(-1)
    six = matrix_to_six_vec(M)
    print(f"hand-eye result: translation={six[:3]}, rotation_rad={six[3:]}")
    if dry_run:
        print("(dry-run) manifest unchanged")
        return 0
    write_extrinsic(mpath, six_vec=six, source="hand_eye_calibrated")
    print(f"wrote extrinsic to {mpath}")
    return 0
