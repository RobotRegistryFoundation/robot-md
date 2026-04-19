#!/usr/bin/env python3
"""Tier 0 experiment #5 — OAK-D scene snapshot with 3D positions.

Captures one aligned RGB + depth frame, reports the 3D position (in
camera frame, millimeters) at a grid of sample points + at the single
closest point in the scene. Saves annotated images to /tmp/tier0/ for
visual inspection.

No hand-eye calibration needed — 3D positions are in CAMERA frame only.
We're *acknowledging* what the camera sees, not transforming to arm frame.

Axis convention (OAK-D): X right, Y down, Z forward (into scene), mm.

    python examples/tier0/05_scene_snapshot.py [--output /tmp/tier0]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

try:
    import depthai as dai
except ImportError:
    print("✗ depthai not installed", file=sys.stderr)
    sys.exit(1)

RGB_SIZE = (1280, 720)       # width, height — RGB capture
DEPTH_SIZE = (640, 400)      # mono cam native resolution used by stereo
WARMUP_FRAMES = 20           # let AE/AWB settle + confidence converge


def _intrinsics(device: dai.Device, socket: dai.CameraBoardSocket, width: int, height: int) -> np.ndarray:
    cal = device.readCalibration()
    return np.array(cal.getCameraIntrinsics(socket, width, height), dtype=np.float64)


def _pixel_to_3d(u: int, v: int, depth_mm: float, K: np.ndarray) -> tuple[float, float, float]:
    """Back-project a pixel + depth into 3D camera-frame coords (mm)."""
    if depth_mm <= 0:
        return (float("nan"), float("nan"), float("nan"))
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    z = float(depth_mm)
    x = (u - cx) * z / fx
    y = (v - cy) * z / fy
    return (x, y, z)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="/tmp/tier0", help="directory to save images")
    args = p.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    rgb_w, rgb_h = RGB_SIZE

    # Read calibration BEFORE opening the pipeline (device only allows one owner).
    with dai.Device() as cal_dev:
        K_rgb = _intrinsics(cal_dev, dai.CameraBoardSocket.CAM_A, rgb_w, rgb_h)
    print(f"RGB intrinsics @ {rgb_w}x{rgb_h}:\n{K_rgb}\n")

    with dai.Pipeline() as pipe:
        # RGB stream on CAM_A
        rgb_cam = pipe.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
        rgb_out = rgb_cam.requestOutput(size=RGB_SIZE, type=dai.ImgFrame.Type.NV12)
        rgb_q = rgb_out.createOutputQueue()

        # Stereo depth on CAM_B (left) + CAM_C (right), aligned to RGB
        left = pipe.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
        right = pipe.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)
        left_out = left.requestOutput(size=DEPTH_SIZE, type=dai.ImgFrame.Type.NV12)
        right_out = right.requestOutput(size=DEPTH_SIZE, type=dai.ImgFrame.Type.NV12)

        stereo = pipe.create(dai.node.StereoDepth)
        stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
        stereo.setOutputSize(rgb_w, rgb_h)
        stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.FAST_ACCURACY)
        left_out.link(stereo.left)
        right_out.link(stereo.right)
        depth_q = stereo.depth.createOutputQueue()

        pipe.start()

        rgb_frame = None
        depth_frame = None
        print(f"Warming up ({WARMUP_FRAMES} frames)…")
        for i in range(WARMUP_FRAMES):
            rgb_msg = rgb_q.get()
            depth_msg = depth_q.get()
            if rgb_msg is not None:
                rgb_frame = rgb_msg.getCvFrame()
            if depth_msg is not None:
                depth_frame = depth_msg.getFrame()  # uint16, mm

        if rgb_frame is None or depth_frame is None:
            print("✗ failed to capture frames", file=sys.stderr)
            return 1

    # At this point the pipeline is torn down; frames are in local numpy.
    print(f"Captured RGB {rgb_frame.shape}  depth {depth_frame.shape} (dtype={depth_frame.dtype})")

    # Save raw.
    rgb_path = out_dir / "scene_rgb.jpg"
    depth_path = out_dir / "scene_depth.png"  # uint16
    heatmap_path = out_dir / "scene_depth_heatmap.jpg"
    cv2.imwrite(str(rgb_path), rgb_frame)
    cv2.imwrite(str(depth_path), depth_frame)

    # Heatmap for humans: clip to 0-2m, normalize, colorize.
    depth_clip = np.clip(depth_frame, 0, 2000).astype(np.float32)
    depth_norm = (depth_clip / 2000 * 255).astype(np.uint8)
    heat = cv2.applyColorMap(depth_norm, cv2.COLORMAP_TURBO)
    cv2.imwrite(str(heatmap_path), heat)

    # Sample grid: 3x3 of (x, y, z) camera-frame positions.
    print("\nSample grid (u,v) → depth → (X, Y, Z) in camera frame [mm]:")
    print(f"  {'label':<10}{'u':>6}{'v':>6}{'depth':>10}{'X':>10}{'Y':>10}{'Z':>10}")
    sample_points = [
        ("tl", rgb_w // 4, rgb_h // 4),
        ("tc", rgb_w // 2, rgb_h // 4),
        ("tr", 3 * rgb_w // 4, rgb_h // 4),
        ("cl", rgb_w // 4, rgb_h // 2),
        ("center", rgb_w // 2, rgb_h // 2),
        ("cr", 3 * rgb_w // 4, rgb_h // 2),
        ("bl", rgb_w // 4, 3 * rgb_h // 4),
        ("bc", rgb_w // 2, 3 * rgb_h // 4),
        ("br", 3 * rgb_w // 4, 3 * rgb_h // 4),
    ]
    for label, u, v in sample_points:
        d = int(depth_frame[v, u])
        x, y, z = _pixel_to_3d(u, v, d, K_rgb)
        if np.isnan(x):
            print(f"  {label:<10}{u:>6}{v:>6}{'(no depth)':>10}")
        else:
            print(f"  {label:<10}{u:>6}{v:>6}{d:>10}{x:>10.0f}{y:>10.0f}{z:>10.0f}")

    # Closest point in the scene (ignoring zero/invalid depth).
    valid = depth_frame > 0
    if valid.any():
        min_depth = int(depth_frame[valid].min())
        vs, us = np.where(depth_frame == min_depth)
        u, v = int(us[0]), int(vs[0])
        x, y, z = _pixel_to_3d(u, v, min_depth, K_rgb)
        print(f"\n  closest : pixel ({u},{v}) depth {min_depth} mm → 3D ({x:.0f}, {y:.0f}, {z:.0f}) mm")

    # Save annotated RGB with sample points + closest.
    annotated = rgb_frame.copy()
    for label, u, v in sample_points:
        d = int(depth_frame[v, u])
        cv2.circle(annotated, (u, v), 6, (0, 255, 255), 2)
        cv2.putText(annotated, f"{label} {d}mm", (u + 8, v - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)
    if valid.any():
        u2, v2 = int(us[0]), int(vs[0])
        cv2.circle(annotated, (u2, v2), 10, (0, 0, 255), 3)
        cv2.putText(annotated, f"closest {min_depth}mm", (u2 + 12, v2 + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
    annotated_path = out_dir / "scene_annotated.jpg"
    cv2.imwrite(str(annotated_path), annotated)

    print(f"\nImages written to {out_dir}/:")
    print(f"  {rgb_path.name}")
    print(f"  {depth_path.name}  (uint16 raw depth, mm)")
    print(f"  {heatmap_path.name}  (turbo colormap 0-2m)")
    print(f"  {annotated_path.name}  (sample grid + closest-point overlay)")
    print("\n✓ scene snapshot complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
