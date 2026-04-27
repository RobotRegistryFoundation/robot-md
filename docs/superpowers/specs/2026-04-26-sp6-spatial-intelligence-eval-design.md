# SP6 — Spatial Intelligence Eval (Two-Track, Manifest-Native, RRF-Attestable)

**Date:** 2026-04-26
**Status:** Design — pending implementation plan
**Sub-project:** 6 (extends the SP1-SP5 cascade; downstream of SP1)

## Problem

robot-md tells a robot *what to do* through ROBOT.md and *how to act* through the SP1 motion server. It does not yet tell us whether the reasoning stack — Claude or any successor — is *good enough* at the kind of spatial generalization humans do effortlessly: tracking occluded objects, inferring full shape from partial views, recognizing graspable regions on novel objects, and choosing stable placements. Bob's first physical pick run on 2026-04-26 surfaced exactly these failures (matte LEGO invisible to stereo, OAK-D mid-trajectory wedge, inner-reach dead zone, novel-object grasps). We are flying blind on which gaps live in the model, the perception stack, the actuation chain, or all three.

For the Anthropic acquisition thesis, "build the brain" is not the bet — Anthropic's models are. The bet is that we can **measure** whether Claude (and its successors) are good enough for embodied robots, **identify** which spatial skills they handle and which they don't, and **publish a registry-attestable score** that becomes the canonical way the field answers that question. Founder-author of *the* spatial-intelligence benchmark for embodied robots is real defensibility, parallel to the EU-compliance moat already shipped at RRF §22-26.

Without SP6, robot-md has no instrument for the load-bearing strategic question: *do we need to build a layer-1 VLA, or are the models good enough?*

## Scope

**In scope (Phase 0 / v1.0.0):**
- A skill taxonomy of 5 testable units: O1 (object permanence), O2 (container reasoning), O3 (partial-view shape), A1 (graspable region on novel objects), A2 (stability-aware placement).
- Two evaluation tracks per unit: a **probe track** (synthetic stimuli → reasoning stack → scored answer) and an **execute track** (physical fixtures → real robot → scored outcome).
- Side-by-side scoring on the probe track: every probe runs against **baseline-Claude** and against the **robot-declared reasoning stack**, with a per-unit delta surfaced.
- A cheap, no-fiducial fixture kit (~$15-25 COTS) using HSV color segmentation and frame differencing for ground truth, with manual operator review as a fallback gate.
- A `spatial-eval:` section in ROBOT.md declaring spec version, opted-in units, workspace dimensions, judge camera, and reasoning-stack endpoints.
- Score JSON with per-unit + per-track + aggregate scores, RCAN-signed by the robot's apikey.
- 9 MCP tools added to the existing `robot-md mcp` server (one server, per SP1-SP5 simplification revisions Rev 1).
- A new optional extra `[spatial-eval]` (or absorption into `[hardware]` if deps overlap).
- Schema additions to `schema/robot-md.schema.json`.
- Reference rig: bob (SO-ARM101 + OAK-D + tabletop).

**In scope (Phase 1 / v1.1.0+):**
- Promotion of the eval to RRF §27: canonical spec, public probe-set mirror, signed score upload, held-out probe re-run, execute evidence audit, RRF counter-signature, public leaderboard.
- Held-out novel-object set rotation per minor version.

**Out of scope** (deferred to v2 / other sub-projects):
- Trajectory continuity (object falls off edge), composite affordances (stack-on-X), tool-use recognition.
- Layer-1 VLA implementation. SP6 deliberately measures whether one is needed before any is built.
- Sim-only execution (Phase 0 is hardware-only; sim is a v2 question once the metric stabilizes).
- Per-skill remediation modules. SP6 produces evidence; remediation lives in future sub-projects.
- Eval for robots without a tabletop workspace (mobile, aerial, etc.).
- Cross-spec-version score comparisons. Each spec version is a closed leaderboard.

## Design

### Strategic frame

SP6 is an **instrument**, not a brain. Its value comes from three properties:

1. **Discriminating.** The probe track answers *can the model reason spatially?* The execute track answers *can the robot act spatially?* When they diverge, the gap localizes itself: probe-pass + execute-fail ⇒ perception or actuation problem; probe-fail + execute-fail ⇒ reasoning problem the model cannot bridge alone. The two-track design exists for this localization.
2. **Defensible.** The held-out probe set + RRF counter-signature make scores hard to game and impossible to self-attest as registry-attested. RRF becomes the canonical authority, parallel to its compliance role at §22-26.
3. **Roadmap-shaping.** Every skill the eval shows Claude flunking is a candidate for the deferred layer-1 VLA work. Every skill it shows Claude handling is one we don't have to build.

### Skill taxonomy (5 units)

Each unit has both a probe-track definition and an execute-track definition. v2 may expand this set.

#### O1 — Object permanence

The robot observes a target object at t=0. An occluder enters the scene and covers the target. The robot must answer "is the target still present, and where?" — and, on the execute track, retrieve the target.

- **Probe input:** stereo pair before + stereo pair after occlusion + scenario header.
- **Probe output:** `{still_present: bool, position: [x, y, z]}`.
- **Probe scoring:** present-flag accuracy (binary) + position L2 with 2 cm tolerance.
- **Execute fixture:** colored cube + opaque cup, slid over by gripper or hand.
- **Execute pass criterion:** target retrieved within 30 s, occluder ROI shows no significant disturbance.

#### O2 — Container reasoning

The target is placed under or inside a known container. The robot must recover the containment relationship and act on it.

- **Probe output:** containment graph `{container: <id>, contained: <id>}`.
- **Probe scoring:** graph match (exact).
- **Execute fixture:** target + 2-3 distinct-color cups; one cup hides target.
- **Execute pass criterion:** robot visits correct container color, target emerges and is lifted ≥5 cm.

#### O3 — Partial-view shape inference

Target is partly hidden by another object; robot must infer full extent enough to grasp safely without colliding.

- **Probe input:** scene with target ~50% occluded.
- **Probe output:** 3D bounding box (8 corners) for the full target.
- **Probe scoring:** IoU vs ground-truth full extent.
- **Execute fixture:** target + stationary occluder partially overlapping target's silhouette.
- **Execute pass criterion:** target lifted ≥5 cm; occluder ROI pixel-diff <5% over the trial (no significant disturbance). Threshold is a v1 tuning parameter; final value chosen during implementation against bob's lighting.

#### A1 — Graspable region on novel objects

Robot has never seen the target; it must identify graspable region(s) and pick orientation.

- **Probe input:** scene + novel object (shape/pose previously unseen).
- **Probe output:** ranked list of 6-DoF grasp poses.
- **Probe scoring:** top-K agreement with human-rated gold grasps.
- **Execute fixture:** held-out novel-object kit (10 items, rotated per minor version).
- **Execute pass criterion:** novel object lifted ≥5 cm and held ≥2 s without drop. Aggregate = pass rate over the 10-object set.

#### A2 — Stability-aware placement

Robot has object in gripper; must choose a placement pose where the object remains stationary.

- **Probe input:** scene + object handle/centroid description + table region.
- **Probe output:** placement pose (x, y, yaw).
- **Probe scoring:** simulated stability outcome at the predicted pose (or labeled gold outcomes for non-simmable cases).
- **Execute pass criterion:** placed object's ROI pixel-diff <2% over 5 s post-release.

### Probe track

#### Substrate

Each probe is a JSON record:
```json
{
  "id": "o1-public-014",
  "unit": "O1",
  "scenario_header": "a red cube is placed on the table; a green cup is then slid over it",
  "frames": ["base64-stereo-pair-t0", "base64-stereo-pair-t1"],
  "question": {"type": "object_location", "target": "red_cube"},
  "ground_truth": "<held-out at scoring time>"
}
```

Frames mix real captures from bob's runs with synthetic renders. Per-run randomization on lighting and scale is applied to synthetic frames.

#### Output format

Structured JSON, not multiple choice. Tolerance bands defined per unit (above). Multiple choice gameably narrows the answer space; structured outputs match what a real robot stack would emit and force the model to commit to coordinates / graphs / boxes / poses.

#### Targeting — both stacks, side-by-side

Every probe-track run produces **two** answer sets:

- **`baseline_claude`** — probes sent directly to Claude via the Anthropic SDK with no robot-specific context. Measures the model alone.
- **`robot_declared`** — probes routed through whatever reasoning chain ROBOT.md declares (default: same Claude; alternative: VLA + Claude, custom planner, etc.). Measures the robot.

Both are scored against the same ground truth. The per-unit delta `robot_declared - baseline_claude` is the load-bearing artifact: equal ⇒ deferring layer-1 was correct; robot ≪ baseline ⇒ the robot's stack is hurting; both flunk ⇒ layer-1 is justified for that skill.

#### Dataset structure

- **Public split:** ~30 probes/unit, shipped at `cli/src/robot_md/spatial_eval/probe/datasets/public/`. Used for dev + CI + first iteration.
- **Held-out split:** ~30 probes/unit, never published. Lives only at RRF in Phase 1; for Phase 0, kept off-repo by the spec maintainer.

CI runs only the public split. Attestable scores (Phase 1) require the held-out split, which only RRF runs.

#### Compute envelope

Full probe-track run (5 units × 30 public probes × 2 stacks = 300 model calls) targets <8 min wall-clock and <$5 of API cost on a developer laptop with prompt caching enabled. The `--baseline-only` flag halves both (single stack ⇒ 150 calls, <$3). Held-out runs add cost only at Phase 1 attestation time and are RRF-orchestrated.

### Execute track

#### Fixture kit (no fiducials)

- **Standard kit (~$15-25 COTS):** 3 distinctly-colored small objects (red cube, blue mug, green bottle), 3 distinct-color paper cups, black foam-core or felt as a high-contrast play surface, optional printable grid mat (free PDF, regular paper) for coarse position reference. No 3D printer required, no AprilTag library.
- **Held-out novel-object set (A1 only, 10 items):** cheap COTS oddities chosen for shape diversity. Rotated by RRF per spec minor version (Phase 1); kept private by maintainer for Phase 0.
- **Judge camera:** phone on a tripod (or second cheap webcam), positioned to see the full play surface.

#### Ground truth — color segmentation + frame differencing

- **HSV color segmentation** locates target objects on the judge frame. Objects are picked up front for separable hue values; OpenCV thresholding gets <5 mm centroid accuracy on a neutral mat under normal room lighting. No fiducial library, no per-rig calibration.
- **Frame differencing** on a region of interest detects motion (object shifted, occluder bumped, placement settled). Sufficient for A2 stability and O3 collision checks without needing absolute pose.
- **Manual review fallback gate:** every trial records video. Trials where auto-scoring confidence drops below threshold are flagged for a 10-second human review on the recorded clip. Keeps the eval honest under ambiguous lighting / occlusion / motion blur.

#### Trial protocol

10 trials/unit × 5 units = 50 trials per full execute run, ~30 s/trial ⇒ ~25 min total on bob.

Per trial:
1. Random fixture placement within a declared region (seeded; RRF can verify the seed in Phase 1; the robot does not see the seed in advance).
2. Pre-trial rig check — camera_extrinsic, gripper home, IK reachability for the trial fixture region. Fails fast and surfaces the bootstrap-cliff gaps from prior pick runs.
3. Robot executes the unit's task.
4. Out-of-band scorer (not the robot itself) reads the judge video + onboard log and emits pass/fail with reason + scorer confidence.

#### Per-unit pass criteria (translated to color/diff)

- O1: target color reappears in gripper region after retrieval; occluder color region unchanged.
- O2: gripper visits correct container color; target color emerges and rises ≥5 cm.
- O3: target rises ≥5 cm; occluder ROI pixel-diff <5% (v1 starting threshold).
- A1: novel-object ROI rises ≥5 cm in z and stays for ≥2 s; no drop event detected.
- A2: post-release ROI pixel-diff <2% over 5 s.

#### Evidence packet

Per run, the bundle contains:
- Recorded judge video for every trial.
- Onboard logs (robot pose, gripper events, perception emissions).
- Per-trial pass/fail with reason + scorer confidence.
- Final ground-truth color centroids per trial.
- Score JSON (below).
- RCAN signature over the bundle root hash.

### Manifest integration

#### ROBOT.md `spatial-eval:` section (optional)

```yaml
spatial-eval:
  spec_version: "1.0.0"
  units: [O1, O2, O3, A1, A2]   # subset allowed; missing units appear as "not_run"
  workspace:
    play_surface_dims_m: [0.30, 0.30]
    judge_camera:
      device: "phone:tripod"
      resolution: [1920, 1080]
  reasoning_stack:
    baseline: "claude:claude-opus-4-7"
    declared: "claude:claude-opus-4-7"
```

`reasoning_stack` values use the form `<provider>:<model-or-stack-id>`. `claude:<model>` resolves through the Anthropic SDK using the standard apikey path; `vla:<endpoint>`, `local:<module>`, and `custom:<entrypoint>` are reserved for v2 routes and rejected by the v1.0.0 schema. v1 supports only `claude:*` identifiers — the strategic bet under test is precisely whether Claude alone is sufficient, so foreign-stack support is deferred until that question has data behind it.

If the section is absent, the robot is ineligible for the eval — no breakage. Schema enforced via `schema/robot-md.schema.json`; first-motion-readiness already gates this.

#### Score JSON

```json
{
  "spec_version": "1.0.0",
  "rrn": "RRN-000000000002",
  "run_id": "<uuid>",
  "timestamp": "2026-04-26T14:30:00Z",
  "tracks": {
    "probe": {
      "baseline_claude": {
        "O1": {"score": 0.87, "n": 30, "passed": 26},
        "O2": {"score": 0.83, "n": 30, "passed": 25},
        "O3": {"score": 0.71, "n": 30, "passed": 21},
        "A1": {"score": 0.66, "n": 30, "passed": 20},
        "A2": {"score": 0.79, "n": 30, "passed": 24}
      },
      "robot_declared":  { "...": "..." },
      "delta_per_unit":  {"O1": -0.03, "O2": 0.0, "O3": -0.07, "A1": 0.04, "A2": 0.01}
    },
    "execute": {
      "O1": {"passed": 7,  "n": 10, "evidence_sha256": "..."},
      "O2": {"passed": 6,  "n": 10, "evidence_sha256": "..."},
      "O3": {"passed": 4,  "n": 10, "evidence_sha256": "..."},
      "A1": {"passed": 5,  "n": 10, "evidence_sha256": "..."},
      "A2": {"passed": 8,  "n": 10, "evidence_sha256": "..."}
    }
  },
  "aggregate": {
    "probe_baseline":  0.77,
    "probe_declared":  0.78,
    "execute":         0.60
  },
  "rcan_signature": "<base64>",
  "evidence_root":  "sha256:..."
}
```

Per-unit scores are first-class. The aggregate is convenience. Cherry-picking by hiding flunked units is impossible — `units` is declared in ROBOT.md and any missing unit appears as `not_run`.

### RCAN attestation

Two layers, visibly distinct:

- **Phase 0 — self-attested.** Robot signs Score JSON with its RCAN apikey. Verifiable provenance, but the robot graded its own homework. Useful for dev, private comparison, CI gates, internal regression tracking.
- **Phase 1 — RRF-attested.** Robot uploads the evidence packet to RRF §27. RRF independently re-runs the held-out probe split and audits ~20% of execute trials by replaying judge video; full re-audit available on challenge. RRF counter-signs the Score JSON. Counter-signed scores are the only ones eligible for the public leaderboard.

Same JSON shape, different signature set. Tooling can render "self-attested" vs "registry-attested" badges off the signature list.

### Versioning + anti-gaming

- Spec version is immutable per release. Scores tagged `1.0.0` are forever `1.0.0`.
- Held-out probe split + held-out novel-object set rotate on minor version bumps (`1.1.0`, `1.2.0`) to defend against memorization.
- RRF leaderboard groups by spec version; cross-version comparisons are explicitly disallowed in the UI.
- Held-out probes are never published; only RRF runs them.
- Execute evidence requires video + judge frames; RRF spot-checks ~20% of trials by default and can re-score on challenge.
- Side-by-side baseline vs declared exposes "declared stack is just relabeled Claude" claims — the per-unit delta is reported in every run.
- Per-unit scores prevent silent unit-skipping; unit set is declared in ROBOT.md.

### Architecture (one MCP server, per SP1-SP5 Rev 1)

The eval lives inside the existing `robot-md` Python package and adds tools to the existing `robot-md mcp` server. There is **no second MCP server**. This conforms to SP1-SP5 simplification Revision 1 ("one MCP server; complexity opt-in").

#### Components

1. **`cli/src/robot_md/spatial_eval/`** (NEW package) — core eval logic, MCP-independent and unit-testable.
2. **`cli/src/robot_md/mcp/tools/spatial_eval/`** (NEW package) — 9 MCP tool entry points; thin wrappers over the core package.
3. **`schema/robot-md.schema.json`** (UPDATED) — adds the `spatial-eval:` object schema.
4. **`pyproject.toml`** (UPDATED) — adds optional extra `[spatial-eval]` (or absorbs into `[hardware]` if deps overlap; decided at implementation time).
5. **`tests/spatial_eval/`** (NEW) — unit, integration, schema, and signature tests.
6. **`docs/superpowers/specs/2026-04-26-sp6-spatial-intelligence-eval-design.md`** (this document).
7. **Phase 1: RRF §27 endpoints** at robotregistryfoundation.org — separate work in the RRF repo, not in robot-md.

#### Module layout (additive to the existing tree)

```
cli/src/robot_md/
├── mcp/tools/
│   └── spatial_eval/
│       ├── __init__.py
│       ├── dry_run.py
│       ├── run_probe.py
│       ├── run_execute.py
│       ├── run_full.py
│       ├── replay.py
│       ├── init.py
│       ├── kit.py
│       ├── verify.py
│       └── submit_to_rrf.py
├── spatial_eval/
│   ├── __init__.py
│   ├── units/
│   │   ├── __init__.py
│   │   ├── o1_permanence.py
│   │   ├── o2_container.py
│   │   ├── o3_partial_view.py
│   │   ├── a1_grasp.py
│   │   └── a2_stability.py
│   ├── probe/
│   │   ├── __init__.py
│   │   ├── runner.py
│   │   ├── stacks.py
│   │   ├── scorer.py
│   │   └── datasets/public/   # held-out lives only at RRF in Phase 1
│   ├── execute/
│   │   ├── __init__.py
│   │   ├── trial.py
│   │   ├── judge.py
│   │   ├── manual_gate.py
│   │   ├── evidence.py
│   │   └── fixtures/
│   │       ├── kit_v1.md
│   │       └── grid_mat.pdf
│   ├── score.py
│   └── rrf.py     # uses existing robot_md.register / RRF client
└── tests/spatial_eval/
    ├── units/
    ├── probe/
    ├── execute/
    ├── schema/
    └── signature/
```

The MCP tool files are thin: parse args, call into `robot_md.spatial_eval.*`, return structured JSON. Core logic stays testable without an MCP harness.

#### MCP tool surface (9 tools)

```
spatial_eval_dry_run         # preflight: rig, manifest, kit visibility, apikey
spatial_eval_run_probe       # probe track. Args: units?, baseline_only?
spatial_eval_run_execute     # execute track. Args: units?, trials_per_unit?
spatial_eval_run_full        # both tracks
spatial_eval_replay          # rescore an existing evidence packet by run_id
spatial_eval_init            # scaffold spatial-eval: into ROBOT.md
spatial_eval_kit             # return BOM + printable mat as MCP resources
spatial_eval_verify          # verify Score JSON signatures
spatial_eval_submit_to_rrf   # Phase 1: upload signed evidence to §27
```

Naming follows existing snake_case (`execute_task`, `vision_find`). All long-running tools stream MCP progress notifications, matching the `discover` pattern (and avoiding the 10 s flake captured in `feedback_robotmd_flaky_mcp_discover_test.md`).

#### New optional extra

```toml
[project.optional-dependencies]
spatial-eval = [
    "opencv-python>=4.9",   # color seg + frame diff + video bundling
    "numpy>=1.26",
]
```

If `opencv-python` is already pulled by `[hardware]` (likely, given `vision_find` exists), absorb `[spatial-eval]` into `[hardware]` instead and document it under SP3's meta-extra section. Decision made at implementation audit time.

### Phase 1 — RRF §27 promotion

Once Phase 0 stabilizes and the v1.0.0 score format stops moving, register the spec as RRF §27. Endpoints follow the §22-26 pattern:

```
GET  /v1/spatial-eval/spec/{version}              → canonical spec JSON
GET  /v1/spatial-eval/probe-set/{version}/public  → public probe split mirror
POST /v1/spatial-eval/runs                        → upload signed evidence + Score JSON
GET  /v1/spatial-eval/runs/{run_id}               → fetch attested score
GET  /v1/spatial-eval/leaderboard?spec_version=…  → ranked attested scores
```

Held-out probes are never served — RRF runs them server-side as part of the audit. Execute audits spot-check ~20% of trials by replaying judge video; full re-audit available on challenge. RRF counter-signs the Score JSON; counter-signed scores are the only ones on the leaderboard.

The `robot_md.spatial_eval.rrf` module reuses the existing RRF client used by `compliance_status.py` and `eu_register.py`. No new auth surface, no new client library.

### Data flow (Phase 0)

```
operator → MCP tool  →  spatial_eval core  →  ROBOT.md loader (existing)
                                          →  reasoning stack(s) via Anthropic SDK
                                          →  judge camera + onboard log
                                          →  judge.py + manual_gate.py (scorer)
                                          →  score.py (aggregate Score JSON)
                                          →  RCAN signing (existing apikey)
                                          →  evidence packet on disk
                                          →  optional rrf.py submit (Phase 1)
```

### Error handling

- **Missing apikey:** `spatial_eval_dry_run` flags it; full run aborts with the existing apikey-reissue guidance (per `project_bob_apikey_state.md`).
- **Camera_extrinsic invalid or missing:** flagged by dry_run; execute track aborts; probe track unaffected. Aligns with existing first-motion-readiness gates.
- **Judge camera unreachable:** execute track aborts with a clear "configure judge_camera in ROBOT.md and verify visibility" message; probe track unaffected.
- **Anthropic API error / rate limit:** probe track retries with bounded backoff; full failure surfaces in Score JSON as `{score: null, error: ...}` per probe rather than aborting the run.
- **Manual review backlog:** trials flagged for manual review do not block the run; they appear as `pending_manual_review` in Score JSON and are filled in by `spatial_eval_replay` after the operator reviews.
- **OAK-D wedge mid-trial** (per `project_robot_md_production_gaps_2026_04_26.md`): execute trial fails with the existing OAK-D recovery hint; subsequent trials reset perception state.

### Testing

- **Unit tests** for each scorer (HSV color seg, frame diff, IoU, containment graph match) against fixed sample inputs.
- **Probe runner** against a mock reasoning stack returning canned answers — validates Score JSON shape, side-by-side delta computation, dataset split handling.
- **Execute simulation:** synthetic mp4 + scripted gripper events drive `judge.py` end-to-end without hardware. Required for CI; CI does not run on real bob.
- **Schema tests** for the ROBOT.md `spatial-eval:` section — round-trip parse + validation + missing-section graceful behavior.
- **RCAN sign/verify roundtrip** using existing apikey infrastructure.
- **Manual nightly-on-bob run** for execute regression coverage. No ARM CI for SO-ARM101 (per existing project constraints).
- **Anti-flake guard** for `spatial_eval_run_*` MCP tools: streamed progress matches the discover pattern; CI tests use generous (≥30 s) timeouts to avoid the 10 s flake captured in prior memory.

### Success criteria (Phase 0)

1. `spatial_eval_dry_run` passes on bob with a freshly scaffolded `spatial-eval:` section.
2. `spatial_eval_run_probe --units O1` produces a Score JSON with both `baseline_claude` and `robot_declared` populated, RCAN-signed, in <60 s for the public split.
3. `spatial_eval_run_execute --units O1 --trials 3` produces a Score JSON + evidence packet, with at least one trial automatically scored and one manually reviewed (sanity-checks both paths).
4. `spatial_eval_replay` on a saved evidence packet reproduces the same Score JSON byte-for-byte (deterministic scoring).
5. `spatial_eval_verify` validates a self-attested Score JSON; rejects a tampered one.
6. Full run (`spatial_eval_run_full`) completes on bob in <40 min with all 5 units enabled.
7. ROBOT.md schema validation rejects malformed `spatial-eval:` sections cleanly.

### Success criteria (Phase 1)

1. RRF §27 endpoints live at robotregistryfoundation.org with the `/v1/spatial-eval/*` surface.
2. `spatial_eval_submit_to_rrf` uploads bob's evidence packet; RRF re-runs the held-out probe split + audits 2 of 10 execute trials per unit.
3. RRF counter-signs the Score JSON; the public leaderboard shows bob's RRN with `attestation: registry-attested`.
4. A second robot (different rig, same spec version) submits and appears on the same leaderboard.

## Dependencies

- **SP1** (Python MCP server wired) — required: SP6 tools land in the same server. Bob's pick task is already blocked on SP1; SP6 is downstream.
- **bob's apikey** — required for any RCAN-signed run. Per `project_bob_apikey_state.md`, signed reissue request is pending.
- **`opencv-python`** — required for color seg + frame diff. Audit the existing `[hardware]` extra; absorb or add `[spatial-eval]`.
- **Existing RRF client** in `robot_md.register` — reused for Phase 1 submission.
- **RRF §27 endpoint work** (Phase 1) — separate work in the RRF repo; can begin in parallel with Phase 0 or after.

## Open questions

1. Does `[spatial-eval]` get its own optional extra, or absorb into `[hardware]`? Decided at implementation-time after auditing the existing extras tree.
2. Phase 1 RRF endpoint shape — confirm the §27 number is unclaimed and matches the existing §22-26 numbering convention.
3. Held-out novel-object set: who curates it for v1.0.0, and where does it live before Phase 1 RRF rotation? Maintainer's private storage in Phase 0.
4. Manual review tooling — full GUI, CLI prompt, or just video link + JSON edit? Resolved during implementation; CLI prompt + video link is the minimal viable surface.

## Notes

- This spec deliberately defers any layer-1 VLA work. Its purpose is to determine *whether* a VLA is needed, per skill.
- The two-track design is the load-bearing decision: probe-only would not catch perception/actuation failures; execute-only would not isolate model versus stack contributions to a failure.
- The no-fiducial fixture choice traded ~5 mm of ground-truth precision for an order-of-magnitude reduction in setup friction. This is the right trade for v1; precision can be reintroduced in v2 if any unit demands it.
- Per SP1-SP5 simplification Rev 1 ("one MCP server"), all SP6 tools land inside `robot-md mcp`. Standalone `robot-md-spatial-eval-mcp` was considered and rejected.
