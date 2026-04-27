# Spatial-Eval Standard Kit v1

Total Phase 0 cost: ~$15-25 (US, 2026 prices). No 3D printer required, no fiducial library, no calibration. The "Standard kit" below is the open published BOM; the held-out novel-object set (A1 only) is rotated by RRF starting in Phase 1.

## Standard kit (open)

| Item | Quantity | Notes |
|---|---|---|
| Solid red small cube (~3-5 cm) | 1 | Wooden block, painted plastic, or LEGO 4×4 stack |
| Solid blue mug (small) | 1 | Distinct from the green cup; matte finish preferred |
| Solid green bottle (small) | 1 | Or a green plastic cup of distinct shape |
| Opaque paper cups (red, green, white) | 3 | Disposable, no logos, opaque to camera |
| Black foam-core or felt sheet | 1, ~40×40 cm | Play surface; matte black for max color contrast |
| Phone tripod (or webcam stand) | 1 | Holds the judge camera ~50 cm above the play surface |

## Held-out novel-object set (A1 only — kept private in Phase 0)

10 cheap COTS objects of varied shape, picked by the spec maintainer. Examples:
tape dispenser, dollar-store animal toy, salt shaker, zip-tie bag, foam ball.

The held-out set rotates per spec minor version starting in Phase 1 (RRF-managed).

## Setup

1. Lay the foam-core flat in a well-lit area; aim for diffuse overhead lighting (avoid shadows on the play surface).
2. Place the phone tripod so the entire 30×30 cm play surface is in frame at the resolution declared in `ROBOT.md` `spatial-eval.workspace.judge_camera.resolution` (default 1920×1080).
3. Arrange the kit objects on the play surface; the trial protocol randomizes their positions per trial within the play surface.
4. Run `spatial_eval_dry_run` MCP tool to confirm the rig + section + apikey are all green before the first run.

## Optional: printable grid mat

The companion file `grid_mat.pdf` (sibling of this file) is intended to print on regular A4/Letter paper as a coarse 1 cm grid for visual position reference. Not required by the auto-scorer (which uses HSV color seg + frame diff against the foam-core background); useful for manual review.

For Phase 0 the actual PDF generation is deferred — `grid_mat.pdf` will be authored in a later content commit using a chosen PDF backend (likely `reportlab` or a hand-drawn PDF). Phase-0 operators who want a grid mat can use any 1 cm × 1 cm grid printout (graph paper at 1 cm spacing also works).

## Color tuning notes

If room lighting causes false negatives in HSV color segmentation, the per-color `ColorParams` defaults in `cli/src/robot_md/spatial_eval/execute/trial.py` (`TARGET_COLORS`) can be overridden via the `spatial_eval_dry_run` calibration path (added in v1.1). For v1.0 the defaults assume normal indoor lighting (~500 lux) on the matte black play surface.

If a target object is matte and unlit, color seg may miss it entirely (this was observed on bob's first pick run with a matte LEGO under hand shadow). Workarounds: add a small ring light, swap to a glossier finish on the cube, or relax `ColorParams.s_min` and `v_min` — the current defaults (s_min=120, v_min=80) are tuned for saturated direct-lit colors.

## Scoring under this kit

- O1 (object permanence): red cube on the play surface; green cup slid over it as occluder.
- O2 (container reasoning): red cube placed under one of the three colored paper cups; robot must identify the right cup and lift to retrieve.
- O3 (partial-view shape): red cube partly hidden by the blue mug; robot must grasp without disturbing the mug.
- A1 (graspable region): each item from the held-out novel-object set is presented in turn; robot must lift each ≥5 cm and hold ≥2 s.
- A2 (stability-aware placement): red cube starts in gripper; robot must place it on a marked region of the play surface and have it remain stationary for 5 s post-release.

All five tasks share the same kit + judge camera + play surface — the held-out novel-object set is the only A1-specific content.
