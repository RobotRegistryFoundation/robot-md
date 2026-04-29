# Spec: hand-eye calibration v2 — fiducial-based, agent-orchestrated

**Status:** design proposal, not yet implemented.
**Target repo:** `~/robot-md` (CLI/types) and `~/robot-md-mcp` (MCP server). Both dev repos.
**Author:** drafted with Craig, 2026-04-27.

## Problem

The existing `robot-md calibrate --extrinsic` mode uses a **gripper-silhouette + wrist-wiggle** algorithm: move the arm through 6 sweep poses, capture depth, shift wrist_flex by a small delta and capture again, diff to isolate the gripper, solve Procrustes from FK gripper position ↔ camera-frame centroid.

In a real session it produced **216 mm and 243 mm residuals** on consecutive runs. The method is fundamentally fragile for typical SO-ARM101 + OAK-D setups:

- **The "marker" is the gripper itself** — small, matte, low-texture. Stereo depth has holes on it. The wiggle-diff becomes "subtract two noisy depth maps and hope the gripper is the largest residual."
- **Six pose samples is too few** for a 6-DoF rigid transform under noise.
- **Operator manual measurement** as the fallback (what we resorted to in the session) is fragile because it requires the operator to decompose a single straight-line distance into per-axis components in the *arm's* frame, which depends on the mounting orientation — a step where the operator and the manifest's `base_frame` convention silently disagree.

The session's session-end measurement put the camera at "23 inches from arm base," which the operator interpreted as straight-line and Claude initially modeled as purely vertical. The math then put a lego on the bowl-table at world arm-z = −545 mm (outside workspace), when it was physically reachable. No amount of HSV-tuning or workspace-bound-loosening fixed it because the underlying transform was wrong.

## Design

A **fiducial-on-gripper hand-eye calibration** that:
1. Uses a **printed visual marker** (ArUco / ChArUco / AprilTag) attached to the gripper at a known offset.
2. Detects the marker corners with subpixel accuracy in each frame (OpenCV `cv2.aruco` is mature; runs on CPU at >100 FPS).
3. Moves the arm through 15–25 poses (vs. 6), all with the marker visible to the camera.
4. Solves AX = XB (or Procrustes on marker-3D-pose ↔ FK-3D-pose) with `cv2.calibrateHandEye`.
5. Expected residual under 5 mm; typical sub-mm on a clean run.

### Operator UX

```
> /calibrate-camera
Bob: I see your gripper has the ArUco-12 marker. I'll move through 18 poses
     to learn the camera-to-arm transform. Workspace clear?
Operator: yes
Bob: Authorizing 18 commanded arm motions on scope `arm`. Starting now.
[runs ~90 s]
Bob: Calibrated. Residual 2.3 mm. Camera is at (-12, +47, +584) mm in arm frame,
     looking down with 4.2° forward tilt. Saved to ROBOT.md.
     extrinsic_source: aruco_handeye_calibrated
```

That's the entire flow. No depth-bound tweaks, no manual measurement, no axis-mapping debate.

### MCP tools

| Tool | Purpose |
|---|---|
| `mcp__robot-md__detect_marker` | Run ArUco detection on the current frame, return `[{marker_id, corners_pixel, pose_camera_frame, confidence}]` |
| `mcp__robot-md__plan_calibration_poses` | Generate N safe poses (workspace-checked, marker-visible-from-camera-checked, joint-envelope-safe) |
| `mcp__robot-md__execute_calibration_sweep` | HiTL-gated: visit each pose, capture marker pose, capture FK gripper pose, return paired list |
| `mcp__robot-md__solve_handeye` | Run `cv2.calibrateHandEye` on the paired list, return `{extrinsic_6vec, residual_mm, per_pose_error}` |
| `mcp__robot-md__commit_extrinsic` | Write to ROBOT.md after operator approves the residual |

These are deliberately separable so the agent can intervene mid-flow ("residual is 4 mm — looks good, committing" vs. "residual is 80 mm and pose 7 had no marker detection — let me re-run with one more pose").

### Slash command

`/calibrate-camera` orchestrates the above. On failure modes:

- **No marker detected at start** → operator instruction in plain English: "I don't see the calibration marker on the gripper. It should be a ChArUco/ArUco patch — print one from `~/.robot-md/marker.pdf` and tape it to the gripper face, then retry."
- **Some sweep poses miss the marker** → agent retries those poses (marker detection sometimes fails at extreme angles); if persistent, reduces sweep diversity.
- **High residual (>10 mm)** → agent surfaces per-pose errors; operator decides: re-run with more poses, or investigate physical issue (mast wobble, marker not flat, arm zero off).

## Closed design decisions

### 1. Marker type: ChArUco

ArUco alone is single-marker, less robust at extreme angles. ChArUco interleaves checkerboard corners with ArUco IDs, gives more correspondence points per detection, and is OpenCV-supported out of the box. A small ChArUco board (e.g., 5×4 ArUco-25 mixed with checkerboard) on the gripper face is enough.

The board is shipped as a printable PDF in `~/.robot-md/marker.pdf` (sized to fit a typical small-gripper face). First-run UX: `robot-md` checks if the manifest's `solver.gripper.marker` block is populated; if not, generates the PDF and prompts the operator to print + tape it.

### 2. Manifest declaration

```yaml
physics:
  solver:
    gripper:
      marker:
        type: charuco
        dict: DICT_4X4_50
        ids: [12, 13, 14, 15]    # the ChArUco corner IDs used
        size_mm: 30               # board edge
        offset_from_tip_mm: [0, 0, -10]   # marker center relative to gripper tip in gripper frame
```

This block is what `detect_marker` consults at runtime. It's a *registered* descriptor (auditable), not in the dynamic store.

### 3. Pose-sweep generation

`plan_calibration_poses(n=18)` returns poses that:
- Lie inside `physics.workspace.bounds_mm`
- Place the marker inside the camera's FOV (predicted via current best-guess extrinsic — bootstrapping)
- Span sufficient orientation variance (Procrustes degenerates if all poses share an axis)
- Pass `analyze_envelope` (no joint near limit, no duty-cycle violation)

Bootstrapping problem: the first calibration has no prior extrinsic, so "marker in FOV" can't be predicted. Solution: the first sweep uses a coarse sweep through the *full* workspace; the agent observes which poses produce successful marker detections and concentrates the next sweep around those. Two-stage: rough sweep (n=12) → refined sweep (n=12). Total ~24 motions, ~2 minutes.

### 4. The mounting-orientation problem stops mattering

Once the calibration is sub-mm, "is the camera 23 inches above or 21 inches forward + 8 inches up" stops being a manual reasoning problem — the math falls out of the AX=XB solve regardless of the operator's intuition about mounting geometry. The session's primary blocker simply disappears.

### 5. Backwards compatibility

The existing `--extrinsic` (silhouette) mode stays in place as a fallback for setups where a marker can't be added. But the docs and the `robot-md doctor` recommendations point at the marker-based mode as the default for new robots.

## Out of scope

- Implementation. This is a spec.
- Multi-camera calibration (each camera calibrates independently against the same gripper marker).
- Continuous (online) recalibration — out of scope; the assumption is the camera-arm rigid mount doesn't drift between sessions.

## Open questions for implementer

- **Marker size vs. arm size.** The SO-ARM101 gripper face is small (~30 mm). ChArUco boards under 25 mm get unreliable corner detection at typical OAK-D RGB resolution + 800 mm working distance. Size needs validation per arm.
- **Where the marker mounts.** Gripper face vs. wrist flange vs. dedicated calibration jig. Gripper face is operator-friendly (no extra hardware) but obstructed during pick. Wrist flange is robust but needs hardware. Default: gripper face, with a "swap to flange" flag for users who want a permanent mount.
- **What if the operator can't print a board?** Fallback: a single saturated-color sticker (e.g., a fluorescent green dot) at known offset. Lower accuracy (centroid only, no corners), but better than the silhouette method.
- **Validating the result.** After calibration, do a verification pose: command the arm to put the gripper at a known world-frame point, observe where the marker actually appears in the camera, report the discrepancy. If >5 mm, surface to operator.

## Companion specs

- `/home/craigm26/perception-architecture-v2-spec.md` — uses the same MCP-tool pattern; the gripper-marker block declared here is consumed by the `detect_gripper` primitive in that spec.
- `/home/craigm26/calibrate-zero-spec.md` — zero-pose calibration. Should run *before* hand-eye (FK accuracy is a prerequisite for hand-eye to converge).

## Why this matters

The session's failure to pick a lego on a clearly-visible bowl-table came down to ~2 cm of camera-pose uncertainty. Sub-mm hand-eye calibration would have made the entire arc — manifest tweaks, extrinsic guesses, axis confusion, IK reach errors, visual servoing — unnecessary. The right ergonomic answer for an operator-facing robot is: print a board, tape it on, run one slash command, done.
