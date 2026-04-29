# `robot-md/proposals/`

Proposals to extend the core ROBOT.md spec. Each proposal is a versioned design document that's actively being evaluated — empirically — by the [`robot-md-autoresearch`](https://github.com/RobotRegistryFoundation/robot-md-autoresearch) eval rig.

## How proposals progress

```
proposals/<slug>.md   ──(eval validates)──▶   spec/<section>.md
   (open, evolving)                              (merged into core spec)
```

Each proposal that lands here has a corresponding spec-seeded variant in `robot-md-autoresearch/variants/specs_seeded/`. When that variant beats `baseline` in the autoresearch loop by ≥5% margin (composite score) and clears the cold-start headline gate, the autoresearch promoter opens a PR proposing to merge the proposal into the core spec.

## Current proposals

| Slug | Source | What it proposes |
|---|---|---|
| `easy-ux-design.md` | drafted with Craig 2026-04-27 | Single-utterance UX, two-layer safety architecture (`hitl_gates` + new `hitl_overrides` block), layered failure UX (silent retry → visual disambiguation → plain-English), 2-min cold-start headline target |
| `perception-architecture-v2.md` | drafted with Craig 2026-04-27 | Descriptor store at `<robot_root>/.bob/objects.db`, Claude-multimodal-as-perception-brain, MCP primitives (`grab_frame`, `depth_at_pixel`, `detect_candidates`, `back_project`), `vision.object_descriptors[]` becomes thin migration target |
| `hand-eye-calibration-v2.md` | drafted with Craig 2026-04-27 | Fiducial-on-gripper auto-calibration; the only manual setup step for DIY robots |
| `calibrate-zero-v2.md` | drafted with Craig 2026-04-27 | Agent-orchestrated zero-pose calibration via MCP tools, no shell |

All four were drafted in the wake of a session that exposed UX friction points during a single physical pick attempt. Proposals are *design proposals, not yet implemented* — that's what `robot-md-autoresearch` is built to test.

## Authoring a new proposal

1. Write the proposal as a self-contained markdown document. Include:
   - **Status:** "design proposal, not yet implemented"
   - **Companion specs:** if the proposal depends on other proposals, list them
   - **Thesis:** one paragraph
   - **Manifest changes:** what fields/sections this adds or restructures
   - **Out of scope** + **Open questions**
2. Add it as `proposals/<slug>.md`.
3. Open a corresponding spec-seeded variant in `robot-md-autoresearch/variants/specs_seeded/<slug>/` so the eval can score it.
4. The autoresearch loop will surface evidence; promotion to the core spec follows from results.

## Why this directory exists

Without `proposals/`, design proposals lived as loose markdown files in a contributor's `~/`. They weren't versioned, didn't have a stable URL, and couldn't be cited from `robot-md-autoresearch`'s `provenance.source.commit`. This directory is the staging ground that closes that gap.
