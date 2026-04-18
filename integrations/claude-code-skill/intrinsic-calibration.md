---
name: intrinsic-calibration
description: Guide operator through checkerboard-based camera intrinsic calibration for a ROBOT.md driver/stream without factory calibration. Triggers when a ROBOT.md has `intrinsic: null` on a camera's primary_stream and the operator asks to calibrate or run the wizard.
---

# Intrinsic calibration — guided operator walkthrough

You are helping an operator run `robot-md calibrate-intrinsic` to fill in a `null` camera intrinsic on a ROBOT.md. Your job is to narrate the session while the CLI does the work.

## The protocol

The CLI drives state via a JSON session file. You poll it; don't guess.

- `robot-md calibrate-intrinsic <ROBOT.md> --driver <id> --stream <name> --session-file <path>` — initializes the session, emits a printable checkerboard PNG next to the session file.
- `--frame <path.png>` — add a captured frame; the CLI updates `coverage`, `frames_captured`, `next_hint`.
- `--finalize` — solves and writes the intrinsic block back into ROBOT.md.

Session-file shape:

```json
{
  "driver_id": "...",
  "stream": "...",
  "board_size": [9, 6],
  "frames_captured": 0,
  "coverage": 0.0,
  "rms_error": null,
  "next_hint": "<guidance>",
  "complete": false,
  "_frames": []
}
```

## The guided flow

### 1. Identify target

Ask the operator for the driver_id and stream name. If they don't remember, run:

```
robot-md validate <path>
```

Each `null intrinsic` warning names the driver + stream. Surface those warnings back to the operator.

### 2. Init the session

```
robot-md calibrate-intrinsic <ROBOT.md> --driver <id> --stream <name> --session-file intrinsic.session.json
```

This writes `checkerboard_9x6.png` next to the session file. Tell the operator to **print it on letter paper at 100% scale** (ruler-check: one square should be ~25 mm on the printout).

### 3. Capture loop

Coach the operator through 8 poses covering the frame corners and multiple orientations:

1. Top-left of frame
2. Top-right
3. Bottom-left
4. Bottom-right
5. Tilted ~30° towards camera
6. Tilted ~30° away from camera
7. Tilted ~30° rotated left
8. Tilted ~30° rotated right

For each photo the operator captures, run:

```
robot-md calibrate-intrinsic <ROBOT.md> --driver <id> --stream <name> \
  --session-file intrinsic.session.json --frame <path.png>
```

Then `cat intrinsic.session.json` to read `frames_captured` and `next_hint`. Narrate the progress ("6/8 captured") and coach if `next_hint` says detection failed (adjust angle, improve lighting, move closer or further).

### 4. Finalize

Once `frames_captured >= 8`:

```
robot-md calibrate-intrinsic <ROBOT.md> --driver <id> --stream <name> \
  --session-file intrinsic.session.json --finalize
```

This solves via OpenCV's `cv2.calibrateCamera` and writes the intrinsic back into ROBOT.md. Verify with:

```
robot-md validate <ROBOT.md>
```

The `null intrinsic` warning for that stream should be gone. Surface the `rms_error` from the session file — under 0.5 is excellent, under 1.0 is acceptable, above 2.0 suggests recapturing with better coverage.

## Do NOT

- Do NOT guess intrinsics from a camera datasheet — calibrate against the physical device the operator is using. Datasheet values drift unit-to-unit.
- Do NOT write the intrinsic block yourself — `--finalize` is the only sanctioned write path; it keeps provenance and rms_error honest.
- Do NOT skip the final `robot-md validate` — missing "warning gone" = silently broken.
- Do NOT attempt to calibrate a stream flagged `derived_from: [...]` (e.g. a depth stream computed from left+right). Those don't have their own intrinsic; they inherit from their sources.

## When this skill does NOT apply

- Operator has factory calibration (OAK-D, RealSense, ZED) — `robot-md init` already populated the intrinsic. This skill is for cameras without one.
- Operator wants extrinsic (hand-eye) calibration — that's a different verb: `robot-md calibrate --hand-eye` (tracked separately).
- The ROBOT.md already validates with no null-intrinsic warnings — nothing to do.
