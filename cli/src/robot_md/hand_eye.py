"""Hand-eye calibration — solve the OAK-D ↔ arm-base extrinsic.

Writes the 6-vector transform to ``physics.solver.camera.extrinsic`` in the
operator's ROBOT.md. Enables a planner with only the manifest + the live
depth stream to project pixel coords into the arm-base frame.

v0 strategy — **single static marker**
---------------------------------------

The operator prints a planar ArUco tag of known size (default 50 mm) and
places it flat on the workspace at a known (x, y) position in the arm-base
frame (z = 0, facing +z). They run::

    robot-md calibrate --hand-eye ROBOT.md --marker-pos 300,0,0 --marker-size 50

The CLI:

1. Grabs one RGB frame + camera intrinsics from the OAK-D via depthai.
2. Detects ArUco markers in the frame (dictionary DICT_4X4_50, id 0 by default).
3. Builds 4 world-frame correspondences: the marker's corners in arm-base
   coords (derived from --marker-pos + --marker-size, flat-on-table).
4. Solves PnP → rotation vector + translation vector = camera pose in
   arm-base frame.
5. Writes ``extrinsic: [tx, ty, tz, rx, ry, rz]`` (mm + radians Rodrigues)
   to the manifest via ruamel.yaml.

Scope note (v0):

* One marker, one frame, single shot. Multi-marker ChArUco averaging and
  multi-pose refinement are improvements left for v1.
* Assumes the marker sits flat (z = 0, normal = +z in arm-base frame).
  If it's tilted the extrinsic will tilt with it — operator should eyeball
  the result by comparing depth map values after calibration.
* Uses OAK-D RGB camera only (not stereo); depth-to-arm-base projection
  then uses the computed extrinsic to map depth pixels to arm-base coords.

Dependencies: opencv-contrib-python (provides cv2.aruco), numpy, depthai.
All optional — the ``vision`` extras install them.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# ArUco dictionary choice — 4x4_50 is cheap to detect and plenty for
# single-marker calibration (50 unique IDs, 4x4 pattern is robust at
# moderate range). Operator can override via --dict.
DEFAULT_DICT_NAME = "DICT_4X4_50"
DEFAULT_MARKER_ID = 0
DEFAULT_MARKER_SIZE_MM = 50.0


@dataclass
class HandEyeResult:
    """Computed extrinsic + diagnostics."""

    extrinsic: list[float]  # [tx, ty, tz, rx, ry, rz] mm + rad (Rodrigues)
    reprojection_error_px: float
    marker_detected: bool
    num_markers_found: int


def _marker_corners_world(
    center_xy: tuple[float, float],
    z: float,
    size_mm: float,
) -> np.ndarray:
    """Return the 4 marker corners in arm-base frame (mm).

    Marker is assumed flat (parallel to the arm-base XY plane), with +x
    toward "right" and +y toward "up" in the marker's own view. The corner
    order matches OpenCV ArUco's top-left-clockwise convention:

        0 ─── 1
        │     │
        3 ─── 2
    """
    cx, cy = center_xy
    half = size_mm / 2.0
    # Top-left, top-right, bottom-right, bottom-left in marker view.
    # On the arm-base XY plane with +y = "up", these map to:
    #   TL: (-x, +y)    TR: (+x, +y)
    #   BR: (+x, -y)    BL: (-x, -y)
    return np.array(
        [
            [cx - half, cy + half, z],  # 0 — TL
            [cx + half, cy + half, z],  # 1 — TR
            [cx + half, cy - half, z],  # 2 — BR
            [cx - half, cy - half, z],  # 3 — BL
        ],
        dtype=np.float64,
    )


def _camera_intrinsics_from_oakd():
    """Pull the RGB camera matrix + distortion from the attached OAK-D.

    Returns (K, dist) — K is 3x3 camera matrix, dist is the distortion
    vector in OpenCV order [k1, k2, p1, p2, k3, ...]. Raises RuntimeError
    if depthai isn't installed or no device is visible.
    """
    try:
        import depthai as dai  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "depthai not installed — install the vision extras:\n    pip install 'robot-md[vision]'"
        ) from e

    with dai.Device() as dev:
        cal = dev.readCalibration()
        # OAK-D RGB is CAM_A by default
        K_raw = cal.getCameraIntrinsics(dai.CameraBoardSocket.CAM_A, 1280, 720)
        dist_raw = cal.getDistortionCoefficients(dai.CameraBoardSocket.CAM_A)
    K = np.array(K_raw, dtype=np.float64)
    dist = np.array(dist_raw, dtype=np.float64).reshape(-1)
    return K, dist


def _capture_frame_oakd():
    """Grab one RGB frame from the OAK-D (1280x720, BGR)."""

    import depthai as dai  # type: ignore[import-not-found]

    with dai.Pipeline() as pipe:
        cam = pipe.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
        out = cam.requestOutput(size=(1280, 720), type=dai.ImgFrame.Type.NV12)
        q = out.createOutputQueue()
        pipe.start()
        frame = None
        for _ in range(15):  # warm-up AE/AWB
            f = q.get()
            if f is not None:
                frame = f.getCvFrame()
        if frame is None:
            raise RuntimeError("no frame received from OAK-D")
        return frame


def solve_from_image(
    image_bgr: np.ndarray,
    K: np.ndarray,
    dist: np.ndarray,
    *,
    marker_center_xy_mm: tuple[float, float],
    marker_z_mm: float = 0.0,
    marker_size_mm: float = DEFAULT_MARKER_SIZE_MM,
    marker_id: int = DEFAULT_MARKER_ID,
    dict_name: str = DEFAULT_DICT_NAME,
) -> HandEyeResult:
    """Detect the ArUco marker and solve PnP. Pure function — no I/O.

    Returns a :class:`HandEyeResult` regardless of outcome; check
    ``.marker_detected`` to branch.
    """
    import cv2

    aruco_dict = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name))
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)
    corners, ids, _ = detector.detectMarkers(image_bgr)

    if ids is None or len(ids) == 0:
        return HandEyeResult(
            extrinsic=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            reprojection_error_px=float("inf"),
            marker_detected=False,
            num_markers_found=0,
        )

    ids_flat = ids.flatten().tolist()
    if marker_id not in ids_flat:
        return HandEyeResult(
            extrinsic=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            reprojection_error_px=float("inf"),
            marker_detected=False,
            num_markers_found=len(ids_flat),
        )

    idx = ids_flat.index(marker_id)
    image_points = corners[idx].reshape(-1, 2).astype(np.float64)
    world_points = _marker_corners_world(marker_center_xy_mm, marker_z_mm, marker_size_mm)

    # solvePnP: wants world points in the frame we want the camera pose IN.
    # Here we pass arm-base coords, so rvec/tvec describe how to go from
    # arm-base to camera (i.e., camera pose in arm-base).
    ok, rvec, tvec = cv2.solvePnP(world_points, image_points, K, dist, flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return HandEyeResult(
            extrinsic=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            reprojection_error_px=float("inf"),
            marker_detected=False,
            num_markers_found=len(ids_flat),
        )

    # Reprojection error — useful diagnostic.
    projected, _ = cv2.projectPoints(world_points, rvec, tvec, K, dist)
    projected = projected.reshape(-1, 2)
    repro = float(np.linalg.norm(projected - image_points, axis=1).mean())

    extrinsic = [
        float(tvec[0][0]),
        float(tvec[1][0]),
        float(tvec[2][0]),  # tx, ty, tz (mm)
        float(rvec[0][0]),
        float(rvec[1][0]),
        float(rvec[2][0]),  # rx, ry, rz (rad, Rodrigues)
    ]
    return HandEyeResult(
        extrinsic=extrinsic,
        reprojection_error_px=repro,
        marker_detected=True,
        num_markers_found=len(ids_flat),
    )


def write_extrinsic_to_manifest(manifest_path: str | Path, extrinsic: list[float]) -> None:
    """Write `physics.solver.camera.extrinsic` via ruamel.yaml (preserves comments)."""
    try:
        from ruamel.yaml import YAML  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "robot-md calibrate --hand-eye needs ruamel.yaml — pip install ruamel.yaml"
        ) from e

    path = Path(manifest_path)
    text = path.read_text()
    if not text.startswith("---"):
        raise RuntimeError(f"{path}: missing leading '---' frontmatter marker")
    end = text.find("\n---", 3)
    if end < 0:
        raise RuntimeError(f"{path}: missing closing '---' frontmatter marker")
    fm_text = text[3:end].lstrip("\n")
    body_text = text[end + 4 :]

    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    data = y.load(fm_text)

    # Set physics.solver.camera.extrinsic = [...]
    phys = data.setdefault("physics", {})
    solver = phys.setdefault("solver", {})
    cam = solver.setdefault("camera", {})
    cam["extrinsic"] = [round(v, 6) for v in extrinsic]

    import io

    buf = io.StringIO()
    y.dump(data, buf)
    path.write_text("---\n" + buf.getvalue().rstrip("\n") + "\n---" + body_text)


def cli_calibrate_hand_eye(
    manifest_path: str,
    *,
    marker_pos: tuple[float, float, float],
    marker_size_mm: float = DEFAULT_MARKER_SIZE_MM,
    marker_id: int = DEFAULT_MARKER_ID,
    dry_run: bool = False,
) -> int:
    """Operator-facing entry point.

    Expects the OAK-D to be plugged in + the ArUco marker physically at
    the specified position in arm-base frame. The marker_pos[0:2] are the
    marker center's (x, y) in mm; marker_pos[2] is z (0 = on the table).
    """
    try:
        K, dist = _camera_intrinsics_from_oakd()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    try:
        frame = _capture_frame_oakd()
    except RuntimeError as e:
        print(f"error: frame capture failed — {e}", file=sys.stderr)
        return 2

    print(
        f"Detecting ArUco marker id={marker_id} "
        f"(size={marker_size_mm:.0f} mm) at arm-base position "
        f"({marker_pos[0]:.0f}, {marker_pos[1]:.0f}, {marker_pos[2]:.0f}) mm...",
        file=sys.stderr,
    )
    result = solve_from_image(
        frame,
        K,
        dist,
        marker_center_xy_mm=(marker_pos[0], marker_pos[1]),
        marker_z_mm=marker_pos[2],
        marker_size_mm=marker_size_mm,
        marker_id=marker_id,
    )

    if not result.marker_detected:
        print(
            f"error: marker id {marker_id} not found in frame "
            f"({result.num_markers_found} other markers visible).\n"
            "  Check: marker printed at the declared size? flat on workspace? "
            "in OAK-D's field of view? lighting adequate?",
            file=sys.stderr,
        )
        return 3

    tx, ty, tz, rx, ry, rz = result.extrinsic
    rx_d = math.degrees(rx)
    ry_d = math.degrees(ry)
    rz_d = math.degrees(rz)
    print(
        f"\n✓ marker detected — solvePnP converged\n"
        f"  extrinsic (camera-in-arm-base frame):\n"
        f"    tx = {tx:+8.2f} mm    ty = {ty:+8.2f} mm    tz = {tz:+8.2f} mm\n"
        f"    rx = {rx_d:+8.2f}°    ry = {ry_d:+8.2f}°    rz = {rz_d:+8.2f}°\n"
        f"  reprojection error: {result.reprojection_error_px:.2f} px"
        f" (lower is better; < 1.0 is good)",
        file=sys.stderr,
    )

    if dry_run:
        print("\n--dry-run: manifest not written.", file=sys.stderr)
        return 0

    try:
        write_extrinsic_to_manifest(manifest_path, result.extrinsic)
        print(
            f"\n  wrote physics.solver.camera.extrinsic to {manifest_path}",
            file=sys.stderr,
        )
    except RuntimeError as e:
        print(f"  warning: could not update manifest: {e}", file=sys.stderr)
        return 2
    return 0
