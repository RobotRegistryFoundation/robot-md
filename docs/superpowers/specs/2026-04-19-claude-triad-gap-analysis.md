# ROBOT.md — gap analysis for Claude Code / Desktop / Mobile

**Date:** 2026-04-19
**Status:** draft
**Context:** End-to-end pick-red-lego-place-in-bowl test on SO-ARM101 with OAK-D
was attempted in a fresh `~/rm-fresh-2026-04-19/` workspace under bare
`robot-md init`. Perception chain validated. Physical pick failed due to
**uncalibrated kinematics**. This doc lists every field, tool, and
convention ROBOT.md needs to add (or expose) so the three Claude
surfaces can close the gap.

---

## Summary

A ROBOT.md that passes `validate` today is a **descriptive** file. Claude
reads it and *knows* things about the robot. It is not yet a **prescriptive**
file — Claude does not know how to *operate* the robot from it alone. The
gap is small and concrete. Ten fixes, listed below.

---

## The pick-and-place failure, decomposed

| Layer | Expected | Actual today | Gap |
|---|---|---|---|
| Scene capture | OAK-D RGB + depth + intrinsic `K` | ✓ works via `ctx.backend._perception.grab_frame()` | none |
| Object detection | `arm.pick(target="red lego")` resolves a 3D point | `detect_objects()` returns `[]`; args ignored | **§3, §6** |
| Arm pose for manipulation | Gripper reaches tabletop when commanded | Zero pose `(2048,…)` is retracted-vertical — gripper 16mm above lego, pan produces negligible gripper motion | **§1, §2** |
| Camera→arm transform | `x_cam` → `x_base` → joint targets | No extrinsic, no IK | **§4, §5** |
| Discovery | Session-to-session learning | Ad-hoc scripts reinvent HSV/probe each session | **§7, §8** |
| Cross-surface parity | Desktop + Mobile get the same info | Mobile via `.well-known/robot-md.json` has no learned skills, no status | **§9** |
| Safety gating | Pre-flight: is robot ready to actuate? | MCP dispatches without precondition checks | **§10** |

Each numbered gap below is a single-field or single-tool change.

---

## §1 — Distinguish *encoder zero* from *manipulation home*

**Today:** `physics.kinematics[].zero_pose_steps` is the encoder-zero
calibration (fine). But every preset sets every joint to 2048 for this
field, which puts the arm in its *retracted* mechanical pose. Nothing
in the manifest says "to manipulate objects, go to this other pose."

**Proposed field:**

```yaml
physics:
  poses:
    ready:
      description: 'Arm extended forward, gripper pointing down at tabletop height.'
      joints: {shoulder_pan: 2048, shoulder_lift: 1600, elbow_flex: 2400, wrist_flex: 2048, wrist_roll: 2048, gripper: 1700}
      source: taught   # or: declared | solved_from_dh
      taught_at: '2026-04-19'
    stowed:
      description: 'Retracted. Safe for transport / power-off.'
      joints: {shoulder_pan: 2048, shoulder_lift: 2048, elbow_flex: 2048, wrist_flex: 2048, wrist_roll: 2048, gripper: 1700}
```

**CLI:** `robot-md pose teach ready ROBOT.md` — torque-off, prompt
operator to pose the arm, read positions back, write under `physics.poses.ready`.

**Backends:** `arm.home` resolves to `physics.poses.ready.joints` unless
overridden. `arm.pick` / `arm.place` use `ready` as the implicit start.

---

## §2 — Declare *workspace limits* explicitly

**Today:** `physics.kinematics[].limits_deg` exists per joint. That's the
mechanical envelope. Nothing says "at the `ready` pose, the reachable
workspace is X-Y-Z box."

**Proposed field:**

```yaml
physics:
  workspace:
    from_pose: ready
    bounds_mm:
      x: [-200, 200]
      y: [50, 300]
      z: [0, 150]
    note: 'Tabletop manipulation envelope. Outside this, IK is not supported.'
```

Claude uses this to refuse motion requests that fall outside the box
*before* computing IK (or when IK isn't wired).

---

## §3 — Capability I/O contracts

**Today:** `capabilities: [arm.pick, arm.place]` are names. The
backend's `arm.pick(args)` accepts `args: dict` and ignores it. Agents
guess what to pass.

**Proposed field:**

```yaml
capability_contracts:
  arm.pick:
    args:
      target:
        kind: object_descriptor    # see §6
        required: true
      approach_height_mm:
        kind: float
        default: 40
    returns:
      status: enum[ok, blocked, error]
      grasped_object: object_descriptor | null
    preconditions:
      - pose.current == poses.ready
      - not estop.set
      - extensions.x-learned-skills.blockers | length == 0
```

Claude Code + Desktop both honor contracts. Claude Mobile displays
them (read-only) so the operator knows what the robot *would* accept
if it had live access.

---

## §4 — Camera extrinsic presence + consumption

**Today:** `physics.solver.camera.extrinsic` is in the spec text; was
never populated by this session's init. `robot-md calibrate --hand-eye`
exists but wasn't run. The MCP doesn't expose "is extrinsic present?" as a
resource.

**Proposed:**
1. Guarantee `physics.cameras[].extrinsic` is either populated (4x4
   matrix) or **explicitly null with a reason**.
2. Add MCP resource `robot-md://robot/calibration_status` that surfaces
   `{zero: ok|missing, sign: ok|missing, hand_eye: ok|missing}`.
3. Preset YAMLs should include an empty `extrinsic: null` stub so it's
   visible in the validator output.

---

## §5 — IK provider is a manifest decision

**Today:** DH params declared. Nothing says "use IK solver X" or "this
robot doesn't support IK yet."

**Proposed field:**

```yaml
physics:
  solver:
    ik_provider: null        # or: inhouse-so-arm101 | urdf-moveit | …
    ik_frame: ready          # IK is solved relative to which named pose
```

Backends check `ik_provider`. If null: `arm.pick_at(pose)` returns
`error: no_ik_declared`. If set: solver runs. The gap is visible in the
manifest, not buried in backend code.

---

## §6 — Object descriptors (the thing capabilities are *about*)

**Today:** `arm.pick(object="red lego")` is a free string. No
vocabulary, no promise the vision stack can resolve it.

**Proposed field:**

```yaml
vision:
  object_descriptors:
    - id: red_lego
      detector: hsv
      params:
        h_ranges: [[0, 10], [170, 180]]
        s_min: 110
        v_min: 80
    - id: white_bowl
      detector: hsv_roi
      params:
        s_max: 80
        v_min: 100
        roi: {u_max: 450, v_max: 360}
```

The pick call becomes `arm.pick(target={ref: red_lego})`. The MCP
resolves it via the declared detector. Claude Mobile can introspect
what the robot *knows how to see*.

This supersedes my ad-hoc `extensions.x-learned-skills.perception` block
in `~/rm-fresh-2026-04-19/ROBOT.md`.

---

## §7 — Learned-skills block is first-class, not `x-*`

**Today:** I wrote `extensions.x-learned-skills` as a stowaway. Nothing
reads it.

**Proposed:**
1. Promote to top-level `learned_skills:` in schema v1.1 (backward
   compatible; old manifests just have `[]`).
2. MCP resource `robot-md://robot/learned_skills`.
3. MCP tool `record_skill(id, data)` so agents append *at runtime*.
4. `using-robot-md` skill lists current `learned_skills` in CLAUDE.md.

Shape:

```yaml
learned_skills:
  - id: red_lego_pick.2026-04-19
    status: blocked
    validated: [scene_capture, hsv_segment_red, hsv_segment_bowl, pan_direction_probe]
    blocked_by: [forward_home_pose_missing, hand_eye_missing, ik_missing]
    notes: 'Vision chain works. Physical pick blocked on calibration.'
```

---

## §8 — The discovery pattern is an MCP verb

**Today:** I hand-wrote `/tmp/probe_pan_direction.py`,
`/tmp/detect_scene.py`, `/tmp/vision_pick.py`. Every session starts from
scratch.

**Proposed MCP tool:**

```
mcp__robot_md__discover(
  steps: [
    {capture: {}},
    {detect: {descriptors: [red_lego, white_bowl]}},
    {probe_direction: {joint: shoulder_pan, delta: 30}},
    {plan: {task: "pick red_lego, place in white_bowl"}},
    {dry_run: true}
  ]
) -> DiscoveryReport
```

Returns a structured report the agent can read and a `learned_skills`
delta it can append via `record_skill`. This is the *first-class
discovery pattern* the user asked for.

---

## §9 — Cross-surface parity (Code / Desktop / Mobile)

Today each surface has a different view:

| Surface | Has | Missing |
|---|---|---|
| Claude Code | Live MCP, stdin/out, Bash tool, camera access | — |
| Claude Desktop | Live MCP (via `claude_desktop_config.json`) | — |
| Claude Mobile | `.well-known/robot-md.json` fetch only — no MCP | Status, learned_skills, discovery log |

**Proposed:** `robot-md publish-discovery` should emit not just the
manifest excerpt but also:

```json
{
  "rrn": "…",
  "robot": "…",
  "manifest_url": "…",
  "calibration_status": {"zero": "ok", "hand_eye": "missing"},
  "learned_skills_summary": ["red_lego_pick.blocked"],
  "last_session": "2026-04-19T20:30:00Z"
}
```

So a Mobile operator asking "can you pick the red lego?" gets "the
vision chain is proven but hand-eye calibration is missing — the
operator on-site needs to run `robot-md calibrate --hand-eye` first."
Not "I don't know."

---

## §10 — Preconditions gate actuation

**Today:** `execute_capability` checks `estop` and `hitl_gates`. That's
it. It will happily dispatch `arm.pick` to a backend that then replays
hardcoded waypoints on an uncalibrated arm.

**Proposed:**
1. Each capability contract has `preconditions:` (§3).
2. `execute_capability` resolves them before dispatch. A failed
   precondition returns `status: blocked` with the specific reason.
3. CLAUDE.md renders the precondition list so the agent can *explain*
   the block instead of guessing.

The current session's failure — "motion executed, lego not picked" —
would instead have been: "blocked: `pose.current != poses.ready`. Run
`robot-md pose teach ready` first."

---

## Priority order (smallest unlocks most)

1. **§1 — `physics.poses.ready` + `robot-md pose teach`** (1 day).
   Alone, this unblocks the demo: teach the ready pose, rewrite the
   session's waypoints relative to it, pick the lego.

2. **§10 — Precondition gating** (1 day, depends on §3 skeleton).
   Agents stop silently failing; they surface what's missing.

3. **§6 — Object descriptors** (2 days).
   Formalizes the HSV-in-manifest pattern proven this session.

4. **§7 — `learned_skills` first-class** (2 days).
   Makes discovery durable across sessions.

5. **§8 — MCP `discover` verb** (3 days).
   Depends on §6 + §7. The pattern becomes a feature.

6. **§4, §5, §2, §3, §9** — structural cleanups, each small once the above land.

**Total:** ~2 weeks of focused work. After which the pick-red-lego
demo becomes a single agent turn, not a two-hour debugging session.

---

## What ships in v0.5.0 (today)

Honest baseline: v0.5.0 is the **description + MCP wiring** layer.
`robot-md init` produces a valid, registered, MCP-wired manifest. Scene
capture works. Hardcoded arm.pick/arm.place waypoints exist for the
first-demo trajectory. Everything else — the perception→pick chain, IK,
hand-eye, learned skills, preconditions — is v0.5.1+.

The marketing copy should say so.
