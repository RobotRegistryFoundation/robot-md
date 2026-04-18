"""robot-md calibrate-intrinsic — checkerboard calibration, session-file driven.

Protocol is stable across wizard-skill iterations: the session file is the
contract. Fields: coverage, rms_error, frames_captured, next_hint, complete,
_frames (internal list of captured frame paths).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


BOARD_DEFAULT = (9, 6)
MIN_FRAMES = 8


def session_init(
    *,
    session_file: Path,
    driver_id: str,
    stream: str,
    board_size: tuple[int, int] = BOARD_DEFAULT,
) -> None:
    session_dir = session_file.parent
    session_dir.mkdir(parents=True, exist_ok=True)
    _emit_checkerboard(
        session_dir / f"checkerboard_{board_size[0]}x{board_size[1]}.png",
        board_size,
    )
    data = {
        "driver_id": driver_id,
        "stream": stream,
        "board_size": list(board_size),
        "frames_captured": 0,
        "coverage": 0.0,
        "rms_error": None,
        "next_hint": "Hold checkerboard at the top-left of the frame, tilted ~30° towards camera.",
        "complete": False,
        "_frames": [],
    }
    session_file.write_text(json.dumps(data, indent=2))


def session_add_frame(*, session_file: Path, frame_path: Path) -> None:
    data = json.loads(session_file.read_text())
    img = _load_image(frame_path)
    found, corners = _detect_corners(img, tuple(data["board_size"]))
    if not found:
        data["next_hint"] = "No checkerboard detected — adjust angle/lighting and retry."
    else:
        data["frames_captured"] += 1
        data["_frames"].append(str(frame_path))
        data["coverage"] = min(1.0, data["frames_captured"] / MIN_FRAMES)
        if data["frames_captured"] >= MIN_FRAMES:
            data["next_hint"] = "Enough coverage — run with --finalize to solve."
        else:
            data["next_hint"] = f"{data['frames_captured']}/{MIN_FRAMES} captured. Vary pose + distance."
    session_file.write_text(json.dumps(data, indent=2))


def session_finalize(*, session_file: Path, robot_md_file: Path) -> None:
    data = json.loads(session_file.read_text())
    if data["frames_captured"] < MIN_FRAMES:
        raise RuntimeError(f"need >= {MIN_FRAMES} frames, have {data['frames_captured']}")
    result = _calibrate(data["_frames"], tuple(data["board_size"]))
    _write_intrinsic_into_robot_md(
        robot_md_file=robot_md_file,
        driver_id=data["driver_id"],
        stream=data["stream"],
        intrinsic=result,
    )
    data["rms_error"] = result.get("rms_error")
    data["complete"] = True
    data["next_hint"] = "Done."
    session_file.write_text(json.dumps(data, indent=2))


# --------------------------------------------------------------------- helpers


def _load_image(path: Path) -> Any:
    import cv2
    return cv2.imread(str(path))


def _detect_corners(img: Any, size: tuple[int, int]):
    import cv2
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.findChessboardCorners(gray, size, None)


def _calibrate(frame_paths: list[str], size: tuple[int, int]) -> dict:
    import cv2
    import numpy as np
    objp = np.zeros((size[0] * size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:size[0], 0:size[1]].T.reshape(-1, 2)
    objpoints, imgpoints = [], []
    h, w = 0, 0
    for p in frame_paths:
        img = cv2.imread(p)
        if img is None:
            continue
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCorners(gray, size, None)
        if not found:
            continue
        objpoints.append(objp)
        imgpoints.append(corners)
    if len(objpoints) < MIN_FRAMES:
        raise RuntimeError("too few frames with detected corners")
    rms, K, D, _, _ = cv2.calibrateCamera(objpoints, imgpoints, (w, h), None, None)
    return {
        "fx": float(K[0][0]), "fy": float(K[1][1]),
        "cx": float(K[0][2]), "cy": float(K[1][2]),
        "width": int(w), "height": int(h),
        "distortion_model": "plumb_bob",
        "distortion_coeffs": [float(c) for c in D.flatten()[:5]],
        "rms_error": float(rms),
    }


def _write_intrinsic_into_robot_md(
    *, robot_md_file: Path, driver_id: str, stream: str, intrinsic: dict
) -> None:
    text = robot_md_file.read_text()
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise RuntimeError("robot_md file has no frontmatter")
    fm = yaml.safe_load(parts[1])
    drivers = fm.setdefault("drivers", [])
    drv = next((d for d in drivers if d.get("id") == driver_id), None)
    if drv is None:
        raise RuntimeError(f"driver '{driver_id}' not found")
    streams = drv.setdefault("streams", {})
    streams.setdefault(stream, {})["intrinsic"] = {
        k: v for k, v in intrinsic.items() if k != "rms_error"
    }
    new = "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---" + parts[2]
    robot_md_file.write_text(new)


def _emit_checkerboard(path: Path, size: tuple[int, int]) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        path.write_bytes(b"checkerboard-placeholder")
        return
    cell = 100
    w, h = size[0] * cell, size[1] * cell
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    for ix in range(size[0]):
        for iy in range(size[1]):
            if (ix + iy) % 2 == 0:
                d.rectangle(
                    [ix * cell, iy * cell, (ix + 1) * cell, (iy + 1) * cell],
                    fill=0,
                )
    img.save(path, format="PNG")
