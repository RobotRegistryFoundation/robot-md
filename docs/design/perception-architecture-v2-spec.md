# Spec: perception architecture v2 + agent-orchestrated primitives

**Status:** design proposal, not yet implemented. Updated 2026-04-27 evening with second-session lessons (drop-and-pick attempt + visual servoing exploration).
**Target repo:** `~/robot-md` (CLI/types) and `~/robot-md-mcp` (MCP server). Both dev repos, out of scope for tonight.
**Author:** drafted with Craig, 2026-04-27.

## Design philosophy

**Extreme ease of use for non-developer operators.** The default user is someone with a robot and a goal — "pick the blue lego, put it in the bowl" — not a robotics engineer. Every primitive should compose into single-utterance workflows. Manifest edits, depth-bound tuning, axis conventions, and IK envelope reasoning should be *inside* the agent's loop, not on the operator's plate.

**Data-rich primitives so the agent can reason.** Every operation that can fail must return enough data for the agent (Claude) to diagnose without reaching past the API: raw frames, all detection candidates with metadata, kinematic envelope details with axis-decomposed reasons, FK + IK trace at every waypoint. The agent is the analyst; the CLI's job is to surface the data, not pre-summarize it into one-line booleans.

**The agent is reactive, not driven.** The operator says "pick the blue lego." Everything between that and a successful pick — choosing among multiple candidates, tightening a depth window, panning the arm to clear an occlusion, switching from one IK branch to another, retrying a failed grasp — happens *autonomously inside the agent's loop*, with the agent observing the data the primitives surface and adjusting in real time. The operator answers questions only when there is genuine ambiguity (which of two visible legos? approve a motion that hits a HiTL gate?). They never tweak depth bounds, joint limits, descriptor params, or workspace bounds by hand.

These three goals reinforce each other: rich data lets the agent be reactive, reactivity lets the operator stay at "pick the blue lego," and ease of use is the result.

## Problem

Two related shortcomings in the current design surfaced repeatedly during a real-world bob session:

**1. Object vocabulary lives in the manifest.** Every object the robot can see is declared as a `vision.object_descriptors[]` entry with explicit HSV params + depth bounds. Adding "remember the blue lego over there" requires editing ROBOT.md. The manifest is meant to be the robot's *identity contract* — auditable, stable, RCAN-provenanced — and shouldn't be churning every time the agent encounters a new object. Worse, HSV with hand-tuned depth bounds is fragile: a lighting change, a scene shift, or a workspace rearrangement breaks the descriptor silently and the detector falls through to whatever red blob is the next-largest in frame.

**2. The CLI's high-level primitives are opaque.** `vision_find(descriptor)` returns `ok | no_match | error`. `execute_capability(arm.pick)` returns `ok | unreachable | blocked`. Every failure mode in a real session needs to be opened up — *which* candidate did HSV pick? *Why* is the IK envelope at risk? *What's* the depth at the centroid? The agent's only path to diagnosis is reaching past the primitives into the package internals (Perception class, raw frames, contour lists, IK solver). That's not an architecture; that's an escape hatch.

These aren't edge cases. In tonight's session every failure required low-level diagnosis: a wrong-blob HSV detection (smaller red object closer to camera won over the actual lego), depth filter rejecting valid depth, IK envelope warnings hiding "elbow at 89.7°" behind a single boolean, extrinsic miscalibration mistaken for axis-mapping error. The agent did all of this by hand; the primitives didn't help.

## Design

Two coupled changes:

### A. Object vocabulary moves to a local vector store

Manifest declares the perception *system*, not the *catalog*:

```yaml
vision:
  descriptor_store:
    backend: sqlite-vec
    path: ./.bob/objects.db   # robot-scoped, sibling to ROBOT.md
  detectors:
    - hsv             # the algorithm, not a tuned instance
    - clip            # planned: image embeddings via on-device CLIP
    - depth_segment
```

Object entries live in the store with two provenance classes:

- **Registered** — the operator (or a calibration tool) added it deliberately. Has RCAN-equivalent provenance (operator id, timestamp, signing). Survives store rebuilds. Used for safety-relevant objects (e.g., e-stop button location, calibration markers).
- **Ephemeral** — agent-added during a session. Cleared on store rebuild or session end. Used for "the red lego at this corner of the table." No safety contract.

Schema for an entry: `id`, `class` (registered|ephemeral), `embedding` (vector), `detector_hint` (which algorithm worked best), `last_known_pose_world_mm`, `created_at`, `created_by`. The HSV-style params (`h_ranges`, etc.) become a per-entry `detector_hint.params` blob, not a separate type — this also gives a path for keeping the existing manifest-declared HSV descriptors working: they get migrated into the store as `class: registered`.

### B. CLI exposes deterministic *primitives*; agent orchestrates the *workflow*

Today's high-level tools (`vision_find`, `execute_capability`) stay — they're auditable and useful for production "do the thing" calls. New low-level MCP tools sit alongside them:

| Tool | Purpose | Mutates state? |
|---|---|---|
| `mcp__robot-md__grab_frame` | Returns RGB + depth + intrinsics from the active camera | no |
| `mcp__robot-md__detect_candidates` | Runs a detector, returns *all* candidates with metadata (pixel, depth, area, embedding) — not filtered to one | no |
| `mcp__robot-md__back_project` | (pixel, depth) → camera-frame XYZ | no |
| `mcp__robot-md__apply_extrinsic` | camera-frame XYZ → world-frame XYZ | no |
| `mcp__robot-md__describe_reachability` | world-frame XYZ → `{ workspace_ok, ik_solution, envelope_risk, suggested_approach_height_mm }` with the *reasons*, not just a boolean | no |
| `mcp__robot-md__plan_pick` | (world-frame XYZ, gripper_state) → trajectory waypoints (no execution) | no |
| `mcp__robot-md__replay_trajectory` | Execute waypoints, dry-run flag, HiTL-gated | yes (motion) |
| `mcp__robot-md__store_descriptor` | Add an entry to the descriptor store; class=ephemeral by default, registered requires extra auth | yes (descriptor store) |
| `mcp__robot-md__query_descriptors` | Lookup by id, by embedding similarity, or by last-known-pose | no |

**Signatures (shape, not full JSONSchema):**

- `grab_frame() → { rgb_b64, depth_b64, K, frame_id }`
- `detect_candidates(detector: str, params: dict, max: int = 8) → [{ pixel, depth_mm, area_or_score, descriptor_match: str|null }]`
- `describe_reachability(xyz_world_mm: tuple) → { workspace_ok, workspace_violation: str|null, ik_status: ok|unreachable|envelope_risk, ik_solution: dict|null, envelope_detail: str|null, recommended_approach_height_mm: float }`
- `plan_pick(xyz_world_mm, approach_height_mm: float|null) → { waypoints, total_motion_estimate_s }` 
- `replay_trajectory(waypoints, dry_run: bool, confirm_token: str|null) → { status, error: str|null, executed_waypoints, final_pose }`
- `store_descriptor(name, embedding, detector_hint, registered: bool, last_known_pose: tuple|null) → { id, persisted_to: str }`

### Slash commands

| Slash command | What it orchestrates |
|---|---|
| `/find` | "Find the X." Agent: grab_frame → detect_candidates → score against descriptor store → return the top candidate with reasoning. If multiple competing matches, surfaces all of them and asks which. |
| `/pick` | "Pick the X." Agent: find → describe_reachability → plan_pick → operator confirm → replay_trajectory. *Crucially*, on any failure (not in workspace, IK envelope risk, multiple candidates), surfaces *why* in plain English and offers the actionable fix ("move the lego ~5 cm closer to the arm" rather than `outside_workspace: True`). |
| `/remember-this` | Agent stores the currently-detected object as an ephemeral descriptor. Operator can later promote to registered. |
| `/where-is` | Query the descriptor store by name, returns last-known-pose and recency. |

The slash commands are MCP prompts, parallel to `/check-safety` and `/brief-me`.

## Closed design decisions

### 1. Two stores, not three

Manifest descriptors and DB descriptors are unified. Existing `vision.object_descriptors[]` entries get migrated into the store as `class: registered` on first run. The manifest field becomes a thin migration target ("declare these on first boot if they're not already in the store"); long-term, descriptors live only in the store. No third "in-memory" tier; ephemeral entries persist to disk so the next session can ask "where was the lego last time?" — they just don't have RCAN provenance.

### 2. Embedding model: deferred, plug-in interface

Hard to commit to a specific model (CLIP, DINO, MobileCLIP, etc.) without device-specific benchmarking. Pi 5 + Hailo-8 NPU has good ML acceleration for common architectures. The spec defines the *interface* (`detector: clip` calls a registered embedding plugin and stores the vector), not the model. v1 implementation can use a small CLIP variant; later versions swap in something faster.

### 3. The descriptor store is robot-scoped

`./.bob/objects.db` (sibling to ROBOT.md), not `~/.robot-md/`. A robot's vocabulary belongs to that robot, not to the host. Multiple robots on one host get independent stores. This also makes per-robot backups straightforward (one tarball with ROBOT.md + objects.db).

### 4. Provenance gates apply to *registered* descriptors only

Motions targeting an ephemeral descriptor still hit `arm` HiTL gates. But ephemeral descriptors don't get the audit trail / RCAN signature that registered ones do — there's no signed claim "this is the e-stop button." Motions targeting a *registered* descriptor get the full RCAN-traceable audit (descriptor id → signature → pick log). That's the safety story: ephemeral is convenient, registered is auditable, both are gated.

### 5. The high-level tools stay

`arm.pick(target=descriptor)` and `vision_find(descriptor)` aren't deprecated. They're the audited "do the thing" interface — for production code, scripts, or operators who want a single call. The new low-level tools are for development, diagnosis, and agent orchestration. Both layers coexist; they share the descriptor store and the same kinematics/perception modules underneath.

### 6. Failure surfaces are *informational*, not just `error`

`describe_reachability` returns reasons in a structure the agent can render to plain English:
- `outside_workspace` → which axis violated, by how much, suggested move direction
- `envelope_risk` → which joint, what angle, how close to limit, alternative IK branch
- `multiple_candidates` → list of competing matches with reasons each was non-decisive

The CLI's existing terse error reasons are kept for backwards compat, but every primitive that can fail returns a *narratable* reason in addition.

## Out of scope

- Implementation. This is a spec.
- Specific embedding model selection (defer to device benchmarking).
- Multi-camera support (current design assumes one active camera).
- Object-pose estimation beyond centroid + depth (no 6-DoF pose for now).
- Replacing the existing manifest entirely. The manifest still owns identity, capabilities, safety, kinematics, and the vision *system* declaration.

## Open questions for implementer

- **Migration path.** Do existing `vision.object_descriptors[]` get auto-imported on first run, or does the operator have to opt in? Auto-import preserves existing behavior; opt-in avoids surprise. Probably auto-import with a one-time confirmation prompt.
- **Where ephemeral descriptors decay.** Cleared on session end? On day boundary? Manual `/forget`? Probably manual + LRU eviction at some store size cap.
- **Multi-robot composition.** If two robot-md installs share a vector DB (a fleet), how do registered descriptors propagate? Probably out of scope for v2 — single-robot first.
- **Audit log integration.** `~/.robot-md/audit/` already exists. Should descriptor-store mutations go there? Yes for registered; ephemeral can stay in the DB only.
- **Slash command UX for ambiguity.** When `/pick the red lego` finds two red blobs, the prompt's question to the operator should include the pixel coordinates + a thumbnail or text description of each. Implementer needs to design the disambiguation UX.

## Companion specs

- `/home/craigm26/calibrate-zero-spec.md` — same pattern (low-level MCP tools + slash command) for the zero-calibration workflow.
- `/home/craigm26/hand-eye-calibration-v2-spec.md` — fiducial-based hand-eye calibration, replacing the failed gripper-silhouette method.
- This spec generalizes that pattern: any robot-md operation that today fails opaquely behind a single CLI boolean is a candidate for the same treatment.

## Second-session lessons (2026-04-27 evening)

A second session attempted a "drop the lego, pick it back up, place in bowl" workflow. It surfaced these additional failure modes that the v2 architecture needs to address:

### Gripper-tip identification is a first-class problem

Closed-loop visual servoing requires reliable gripper-tip detection. HSV blue tape (which the operator added to the gripper) is **not enough** when the scene contains other blue objects — the algorithm picks different blobs as "the gripper" between runs as scene composition changes, making the empirical Jacobian noisy and divergent. v2 must include:

- A **gripper marker spec** in the manifest (separate from `vision.object_descriptors[]`) declaring the marker type (color patch, ArUco, AprilTag, ChArUco), expected size, and expected position relative to the gripper FK.
- A **`detect_gripper`** MCP primitive that uses the marker spec, with FK-position-prior to disambiguate from scene clutter.
- The manifest's `solver.gripper.marker:` block holds this declaration, validated and rendered in `doctor`.

This is a separate concern from object-vocabulary descriptors and must not share infrastructure with them — operator-added "remember this object" entries should not pollute the gripper-tracking pipeline.

### IK constraint reasons must be axis-decomposed

IK errors during the session looked like:
- `outside_workspace: True` (which axis? by how much? which direction would help?)
- `ik_failed: target unreachable: need 452.5mm, max 250.0mm` (max 250 was the *2-link planar reach*, opaque to the operator; the actual constraint was a hard-coded "gripper points down" assumption that forced wrist-target perpendicular)
- `envelope_risk: elbow_flex=89.7° is 100% of envelope` (was the envelope conservative, or did this configuration actually risk a latch?)

`describe_reachability` must return:
- For workspace violations: per-axis `(violated_axis, target_value, bound, suggested_move_mm)`.
- For IK failures: which constraint bound (joint limit, planar 2-link reach, gripper-orientation constraint), and which alternative IK branches were tried.
- For envelope warnings: which joint, what angle, distance from limit, and whether the current envelope is conservative (declared margin) vs hard limit (servo specification).

The agent translates these into actionable plain-English suggestions ("the lego is 5 cm below the arm's vertical reach — raise it 5 cm or lower the arm mount"). The CLI provides the data; the agent does the synthesis.

### The mounting orientation problem

The session's bob is mounted with the arm extending sideways from a vertical mast, camera on top of the mast. The manifest's `base_frame: {up: z, forward: x}` is a kinematic-chain convention, not a world-mounting declaration. When the arm is desktop-mounted, those align; when it's mast-mounted, they don't, and every "the arm extends in +x at zero pose" assumption needs explicit re-derivation. Worse, the workspace bounds are in arm-frame, but the operator thinks in world-frame ("the lego is 17 inches below the table mount").

Add `mount` to the manifest:
```yaml
physics:
  mount:
    type: vertical_mast | horizontal_table | wall_plate | ceiling
    base_to_world_transform: [tx, ty, tz, rx, ry, rz]   # arm-base frame in world frame
```

Then `doctor` and `describe_reachability` can render workspace bounds and reach errors in world-frame *and* arm-frame, so the operator's mental model and the kinematics agree.

### Multi-candidate detection by default

`vision_find(descriptor)` returns one match. Tonight's session repeatedly hit the wrong-blob trap: actual lego at depth 1049 mm was filtered out by `max_depth_mm: 700`, and a smaller-but-in-range red marker on the arm itself won the "largest red blob" contest. The agent only saw `ok` with wrong coordinates.

Replace with `detect_candidates(descriptor)` returning *all* matches (and explicit *near-misses* with reasons each was rejected: `out_of_depth_window`, `too_small`, `outside_workspace`, etc.). The agent picks. This is more verbose for the API but makes the failure mode visible — the wrong-blob trap is impossible if the agent sees the in-range candidate alongside the rejection reasons.

### Hot-reload of descriptor params

Every depth-bound tweak (`max_depth_mm: 700 → 1500 → 1080`) required a manifest edit + `validate` + restart of the perception subprocess. For tonight's work that was 6+ cycles. Hot-reload should be a first-class capability:

- `set_descriptor_param(id, key, value)` MCP primitive: applies the change to the in-memory store, mutates the on-disk descriptor entry (registered or ephemeral), no restart.
- The agent uses this naturally during `/find`: "I see two competing red blobs; let me tighten the depth window to disambiguate" → tool call → re-detect → continue.
- Manifest-declared descriptors stay validated; the hot-reload writes to the descriptor store and the migration layer keeps the manifest as a snapshot.

### Drop-and-re-detect requires temporal tracking

After the gripper opened and dropped the lego, the descriptor's "last_known_pose" was stale (still pointed at the gripper position from before the drop). The agent had to re-discover the lego from scratch.

The descriptor store should support:
- `update_pose(descriptor_id, new_world_xyz_mm)` for tracked objects.
- An `is_held_by_gripper: bool` flag per ephemeral descriptor — when true, the pose follows the gripper FK; when false (e.g., after gripper opens), it's frozen at last-observed position.
- A `/drop` slash command that opens the gripper, captures a fresh frame, and updates the descriptor's pose to wherever the object lands.

## Why this matters

The session that prompted this spec spent an hour on calibration and pick attempts that all surfaced as one-line errors (`outside_workspace`, `invalid_depth`, `ik_failed`, `envelope_risk`). Every diagnosis required the agent to bypass the CLI and read package internals. The robot has all the data — frames, depths, candidate lists, kinematic envelopes — but the CLI's interface is too narrow to expose it. This spec widens the interface so the agent can do its job using the tools robot-md publishes, instead of around them.
