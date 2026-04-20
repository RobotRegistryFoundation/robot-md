# Changelog

All notable changes to `robot-md` are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.6.3] — 2026-04-20

### Fixed — hardware bring-up lessons

First hardware bring-up of the v0.6.2 pipeline on a real SO-ARM101 + OAK-D exposed five bugs. All shipped here; `arm.home` now actually moves the arm and holds it.

- **`Perception._spec` stash.** `Perception.from_spec` plucked only `driver_id` from the spec and dropped the reference, so direct callers of `Perception.vision_find(descriptor=...)` got `{'status': 'error', 'reason': 'no_spec'}`. Arm.pick worked through a different code path; debugging calls and non-backend callers broke. `from_spec` now keeps the full spec; `_vision_xyz_cam` also passes it explicitly.
- **Single-waypoint motion.** `motion.replay` for a single-waypoint trajectory was firing a one-shot goal write and returning immediately. Callers (`_do_replay`, `_execute_pick_or_place`) then dropped torque in a `finally` block before STS3215 servos crossed their deltas — net: arm.home reported ok but the arm barely moved. Single-waypoint path now interpolates from the current read-back position, and the existing multi-waypoint path guards `estop=None` so direct Python callers don't crash.
- **Torque-hold after successful motion.** Capability dispatch previously dropped torque unconditionally in a `finally` block, so the arm went limp after every `arm.home` / `arm.pick`. Torque now stays on after a successful motion — the arm holds the final pose. Callers that want limp (teach-mode, shutdown) drop torque explicitly.
- **IK joint-limit enforcement.** `Kinematics.ik_reach` solved for gripper-pointing-down but didn't check the solved angles against each joint's declared `limits_rad`. On SO-ARM101, the tabletop target `(200, 0, 50)` produced `wrist_flex = 94.7°` — beyond the ±90° envelope. The servo stalled, tripped into overload protection, and stopped responding on the bus. `ik_reach` now raises `KinematicsError` with a specific reason when any solved angle is out of envelope.
- **SO-ARM101 preset ships a safe `ready` pose.** Even within the ±90° limit, ik_reach puts wrist_flex near 80° for most tabletop targets — sustained gravity load at that angle trips the STS3215. The preset now ships `physics.poses.ready` with all joints near center (gripper forward, wrist neutral); `phase_auto_calibrate_ready` sees it and skips IK. Arm.pick still solves gripper-down geometry at motion time, transiently — the problem was only holding that pose indefinitely.

### Changed

- `auto_calibrate.compute_ready_pose` default target moved from `(200, 0, 50)` to `(200, 0, 20)` so fallback IK on presets without a declared `ready` stays within ±90° envelopes.
- Schema reminder: `physics.poses.<name>.source` accepts `declared | taught | solved_from_dh` — the preset's ready pose now uses `declared`.

### Compatibility

- v0.6.2 manifests validate and load unchanged. Re-init against the so-arm101 preset to pick up the safe `ready` pose, or copy the `physics.poses.ready` block from `presets/so_arm101.yaml` into an existing manifest by hand.

---

## [0.6.2] — 2026-04-20

### Fixed

- **Preset default extrinsic rotation.** The `so-arm101` preset shipped in v0.6.1 with a 6-vec whose rotation pointed the camera +z axis up-and-back (into the ceiling) instead of at the workspace. Replaced with the result of `from_mount(position=(400, 0, 300), look_at=(200, 0, 0))` — camera +z now points at the workspace center, so typical tabletop detections map to reachable grasp targets in the base frame.
- **Dependency pin for `typer<0.17`.** typer 0.17+ defines `TyperChoice(click.Choice[ParamTypeValue])`, which requires `click.Choice` to be subscriptable. click 8.x (shipped on Python 3.13) does not support that; the subscription raises `TypeError` at import time, tripping pytest collection for anything that imports typer. Pinned to the last 0.16.x line until click 9 is widespread.
- **`CliRunner.stderr` access.** `test_init_non_interactive` used `hasattr(result, "stderr")` which is True on click 8.x Result, but accessing the property raises when stderr wasn't separately captured. Switched to `result.stderr_bytes` directly.

### Changed

- Site hero + §05 demo updated to reflect the v0.6.1 auto-calibrate + `arm.pick` story; the hero's phase [5/5] no longer prompts "teach `ready` pose" (it's auto-solved), and §05 shows the full `arm.pick` → `arm.place` phase decomposition.

### Compatibility

- v0.6.1 manifests validate and load unchanged. If you want the corrected extrinsic for an existing manifest, re-init against the preset or overwrite `physics.solver.cameras[0].extrinsic` by hand with `[400, 0, 300, -2.5536, 0, 1.5708]`.

---

## [0.6.1] — 2026-04-20

### Added

- **Auto-calibrate ready pose.** `robot-md init` on SO-ARM101 now solves a canonical `ready` pose from DH params via the in-house IK solver and writes it to `physics.poses.ready` automatically — no `pose teach` step required. Opt out with the internal `do_auto_calibrate=False` flag.
- **Default camera extrinsic.** `so-arm101` preset ships a default 6-vec extrinsic for the canonical OAK-D-on-tripod mount. Tracked via the new `physics.solver.cameras[].extrinsic_source: preset_default` field.
- **`arm.pick(target)` end-to-end.** The stub is replaced with a real pipeline: `target` (descriptor ID) → `vision.find` → `camera_to_base` → workspace bounds check → `ik_reach` → hybrid trajectory (joint-space approach, cartesian descent, grasp, lift) → `motion.replay`. Same shape for `arm.place(target)`.
- **Hand-eye calibration (opt-in).** `robot-md calibrate --hand-eye ROBOT.md --marker-pos x,y,z` drives an 8-pose ArUco sweep and writes a refined extrinsic, flipping `extrinsic_source` to `hand_eye_calibrated`. Uses `cv2.calibrateHandEye` (Tsai).
- **Doctor warning for preset-default extrinsic.** `robot-md doctor` now warns (not errors) when extrinsic is still a preset guess, pointing users at the hand-eye verb.
- **Capability contracts for arm.pick / arm.place / arm.home.** so-arm101 preset declares preconditions (`pose_taught:ready`, `extrinsic_present`, `ik_provider_set`, `workspace_declared`, `backend_resolved`) that the v0.6.0 evaluator enforces.
- **Workspace bounds on the so-arm101 preset.** `physics.workspace.bounds_mm` declares the reachable envelope so arm.pick can refuse targets outside it before motion.
- **Pure extrinsic math module (`robot_md.extrinsic`).** `six_vec_to_matrix`, `matrix_to_six_vec`, `camera_to_base`, `from_mount`. XYZ extrinsic Euler convention.
- **Trajectory planner (`robot_md.trajectory`).** `plan_pick` / `plan_place` return ordered `Waypoint(phase, joints, settle_ms)` lists with cartesian linear descent.
- **OAK-D driver declared on the so-arm101 preset** (`drivers[].id=oakd, protocol=depthai`) so the camera driver_id cross-reference validates.

### Changed

- `physics.solver.ik_provider` set to `inhouse-so-arm101` on the so-arm101 preset (activates the in-house 3-link planar IK solver already present since v0.5.0).
- Feetech backend's `_arm_pick` / `_arm_place` no longer replay hardcoded waypoints; both are target-driven through the new trajectory planner.
- `hand_eye.py` replaces the v0.5.0 single-shot PnP path with the AX=XB sweep; `write_extrinsic` now writes to `physics.solver.cameras[0].extrinsic` (plural) with provenance tracking.

### Compatibility

- v0.6.0 manifests validate and load unchanged.
- Manually-taught `physics.poses.ready` from v0.6.0 is preserved during re-init (auto-calibrate is idempotent when `ready` already exists).

### Known issues

- The preset-default extrinsic's rotation is a geometric placeholder — it validates and passes all unit tests but does not match a realistic "camera looking down at tabletop" orientation. Users who need accuracy beyond the LEGO-scale tolerance should run `robot-md calibrate --hand-eye`. The doctor warning points at this.

---

## [0.6.0] — 2026-04-19

### Added — closes the Claude-triad gap spec §1–§10

- **`physics.poses`** in manifest + `robot-md pose teach <name> <path>` CLI verb. `arm.home` backend capability now targets `physics.poses.ready` when present (gap §1).
- **`capability_contracts`** with six precondition kinds (`pose_taught`, `extrinsic_present`, `ik_provider_set`, `workspace_declared`, `learned_skill_ok`, `backend_resolved`). `execute_capability` gates on them; read-only caps bypass (§3 / §10).
- **`vision.object_descriptors`** (`hsv` + `hsv_roi` detectors) and the `vision.find` MCP tool — descriptor id → camera-frame XYZ (§6).
- **`learned_skills`** top-level array + MCP `record_skill` tool + three new MCP resources (`robot-md://<name>/{learned_skills, calibration_status, poses}`, all `application/json`) (§7).
- **`discover`** MCP tool — declarative `capture` + `detect` + `probe_direction` pipeline (§8).
- **`physics.workspace`** bounds with per-axis mm ranges (§2).
- **`physics.solver.ik_provider`** + **`ik_frame`** schema fields (§5).
- **`publish-discovery`** now emits `calibration_status` + `learned_skills_summary` — Mobile operators see real status without MCP (§9).
- Generated **`CLAUDE.md`** renders new "Named poses" and "Known skills & blockers" sections.
- **so-arm101 preset** ships `red_lego` + `white_bowl` object descriptors out of the box.
- Init phase `teach_poses` offers to record `ready` on TTY.

### Changed

- `calibration_status` resource now actually inspects `physics.kinematics[].zero_pose_steps` instead of unconditionally reporting `"ok"`.
- Backend `detect_objects(descriptors=…)` routes through `robot_md.detectors.hsv` instead of returning `[]`.
- `execute_capability` precondition gate runs AFTER estop (estop always wins); read-only capabilities bypass both gates.

### Compatibility

All new fields are optional. v0.5.0 manifests validate and run unchanged. v0.6.0 deprecates the stowaway `extensions.x-learned-skills` pattern in favor of the top-level `learned_skills:` block.

---

## v0.5.0 — 2026-04-19

### Added
- `robot-md init` default flow now folds MCP install, skill install, and
  zero/sign calibration into the single command. TTY + hardware detection
  gates the interactive phases; headless / CI callers auto-skip cleanly.
- New flags: `--non-interactive` (scripted callers — manifest-only),
  `--no-install-mcp`, `--no-install-skill`, `--no-sign`, `--no-calibrate`.
- New module `robot_md.install_mcp_claude_code` — subprocess wrapper around
  `claude mcp add` that returns a `PhaseResult` rather than raising.
- New package `robot_md.init_phases` — each phase of init is an independently
  callable library function returning a uniform `PhaseResult`.

### Changed
- `robot_md.init.quick` renamed to `non_interactive`; `quick` kept as a
  deprecated alias that prints a one-time note to stderr.
- `robot-md init --wizard` now an alias for the default flow (the two paths
  are identical). Emits a one-time deprecation note.
- Generated `CLAUDE.md` template now advertises all six MCP tools
  (`validate`, `render`, `estop`, `estop_clear`, `execute_capability`,
  `execute_task`) and points the motion row at `execute_capability`.

### Migration
- Scripted callers relying on `robot-md init` being non-interactive must
  add `--non-interactive`. On CI machines this is the recommended invocation.
- External code importing `robot_md.init.quick` should switch to
  `non_interactive`. The old name still works but warns on each call.

---

## [0.4.1] - 2026-04-18

Dev ergonomics release. Live local dashboard + two safety patches from the v0.4.0 E2E smoke findings.

### Added

- **Dev dashboard** (`robot-md dashboard serve`): local FastAPI+HTMX page on
  `http://127.0.0.1:8091` showing live servo positions, last OAK-D frame,
  tool-call log, estop state, and validator warnings. Localhost-only, no auth.
- **JSONL event log** at `~/.robot-md/events.jsonl` — durable record of every
  MCP tool call + state change, written non-blockingly by an in-server
  `EventPublisher`. Rotates at 10 MB. Backs future `robot-md replay` and the
  v0.8 memory-sync feature.
- **Command channel** at `~/.robot-md/commands.jsonl` — dashboard writes,
  MCP server reads, mutates state. Commands supported: `estop.set`,
  `estop.clear`, `snapshot`.
- **`estop_clear` MCP tool** (fixes #2). HITL-gated on the `system` scope by
  default; pass a `confirm_token` to clear when the gate is declared.

### Fixed

- **#1 — read-only capabilities no longer blocked by estop.** `status.report`
  and `vision.describe` execute even when the estop flag is set. New
  `CapabilityBackend.read_only_capabilities: frozenset[str]` declares which
  capabilities skip the gate; the `feetech_depthai` backend declares those
  two. Motion-producing capabilities are unaffected.

### Added dependencies

- `fastapi>=0.110`, `jinja2>=3.1`, `websockets>=12` (base deps)
- `pytest-asyncio>=0.23` (dev extra)

### Opt-out

- Set `ROBOT_MD_DASHBOARD_DISABLED=1` to disable the publisher + command
  watcher if the MCP server runs in a constrained environment (e.g., a
  container without a writable home).

---

## [0.4.0] - 2026-04-18

Phase 1 of the adaptive backend plan (spec:
`docs/superpowers/specs/2026-04-18-feetech-depthai-real-backend-design.md`).
The `feetech_depthai` backend goes from stubs to real hardware drivers.

### Added

- **Real STS3215 wire protocol** in `backends/feetech_depthai/servo.py` —
  ports the proven code from `examples/tier0/01..04`. ServoBus supports
  `open/close`, `read_positions` (skips non-responders), `write_positions`,
  `torque(on/off)`, and `interpolate(start, target, hz, max_steps_per_tick,
  estop)` with per-tick E-stop checks.
- **Real OAK-D pipeline** in `backends/feetech_depthai/perception.py` —
  ports `examples/tier0/05_scene_snapshot.py`. Reads factory intrinsics,
  builds an RGB + stereo-depth pipeline aligned to RGB, exposes
  `grab_frame() → (rgb, depth, K)`. 3D back-projection helper `_pixel_to_3d`.
- **Trajectory replay** in `backends/feetech_depthai/motion.py` — iterates
  consecutive waypoint pairs, calling `ServoBus.interpolate` between them.
  Single-waypoint trajectories dispatch as one-shot position commands.
- **Real capability handlers** for `arm.pick`, `arm.place`, `arm.reach`,
  `vision.describe`, `status.report`. `arm.pick` / `arm.place` replay a
  hardcoded first-demo trajectory (small joint deltas around zero pose) —
  swapped for skill-store lookup in Phase 2.
- **Hardware smoke tests** (`--run-hardware`) for servo read + nudge and
  OAK-D frame capture.

### Added dependency

- `feetech-servo-sdk>=1.0` joins the `feetech-depthai` optional extra.
  Install with `pip install robot-md[feetech-depthai]`.

### Scope note

`arm.pick`/`arm.place` in v0.4.0 replay a hardcoded trajectory embedded in
the capability handler. Real grasps arrive in v0.5.0 (Phase 2 — skill store).
Perception is opened but not yet consulted during motion (Phase 3);
pose-adjust and hand-eye are Phase 4. See the spec for the full rollout.

---

## [0.3.1] - 2026-04-18

Follow-up patches from the v0.3.0 final review.

### Changed

- **Safety ordering.** `execute_capability_tool` now checks the
  process-wide E-stop before evaluating the HITL gate. E-stop is a
  hard-stop signal that should outrank any consent workflow; this
  matches the spec's intent and eliminates a theoretical race where a
  gate satisfied between estop-set and dispatch could slip through.
- **`RobotSpec.MetadataBlock`** gains a `device_id: str | None` field.
  Backends that want to log or report a robot's per-unit identity no
  longer need to re-parse `raw_yaml`.
- **Documented token semantics.** `_gate_satisfied`'s docstring now
  states plainly that v0.3's `confirm_token` is an opaque stub — not
  verified, not single-use, not scope-bound. Cryptographic tokens
  land in v0.4 per the original spec's out-of-scope list.

### Removed

- **Dead `probe_cameras()` in `autodetect.py`.** Replaced by the typed
  `probe_depthai_cameras` / `probe_realsense_cameras` /
  `probe_v4l2_cameras` probes in v0.3.0; the legacy function was left
  defined but uncallable. Gone now.

### Docs

- **`docs/mcp-server-options.md`** — side-by-side comparison of the
  npm TypeScript MCP and the Python MCP, with registration snippets
  for each. README points at it.

---

## [0.3.0] - 2026-04-18

Camera intrinsics, Python MCP server (as an alternative to the TypeScript
npm `robot-md-mcp`), and pluggable backends. Both MCP implementations
coexist — users pick whichever fits their install story; tools are
protocol-compatible.

### Added

- **Camera intrinsics in schema.** Per-stream `intrinsic` block on
  `drivers[].streams[]` (fx/fy/cx/cy/width/height + distortion model).
  `physics.solver.cameras[]` cross-references `drivers[].id` and carries
  deployment-specific mount + extrinsic. Autodetected from factory
  calibration at `robot-md init` for OAK-D (depthai), RealSense stub,
  and v4l2 (emits `null` intrinsic + provenance note).
- **Python MCP server** shipped as `robot-md-mcp` entry point. New
  tools: `estop` (process-wide software E-stop), `execute_capability`
  (deterministic primitive with HITL gate enforcement),
  `execute_task` (natural-language prompt → planner → capability
  sequence via `brain.planning` declared in the manifest).
- **Pluggable `CapabilityBackend`** interface. Backends register via
  Python entry points under `robot_md.backends`; resolution is
  alphabetical by backend name, with optional `drivers[].backend`
  override. Reference `feetech_depthai` backend ships in-repo
  (install with `pip install robot-md[feetech-depthai]`).
- **`robot-md calibrate-intrinsic`** — session-file-driven checkerboard
  calibration CLI. Init generates a printable 9×6 checkerboard PNG;
  `--frame` captures advance coverage; `--finalize` solves via OpenCV
  and writes the intrinsic block back into ROBOT.md.
- **`integrations/claude-code-skill/intrinsic-calibration.md`** — guided
  wizard skill that drives the CLI through its stable JSON session
  protocol.
- **`robot-md mcp <path>`** convenience subcommand (same as running
  `robot-md-mcp <path>` directly).

### Changed

- **Validator** gains a `warnings` list. Null intrinsic on a
  `primary_stream` surfaces as a warning (with a pointer to
  `robot-md calibrate-intrinsic`); legacy singular
  `physics.solver.camera` emits a deprecation warning after being
  auto-upgraded at parse time.
- **Presets** migrated to the `cameras[]` shape. ALOHA 2 now declares
  four cameras with matching driver entries; arm-only presets
  (SO-ARM101, UR5e, Franka, Koch) no longer bundle a camera block.

### Deprecated

- `physics.solver.camera` (singular) — still auto-upgraded at read
  time; validator emits a deprecation warning. Removed in v2.

### Notes

- The TypeScript npm `robot-md-mcp` continues to be maintained in
  parallel (current: v0.2.1+). The new Python MCP server is an
  alternative install path, not a replacement. Both speak the same
  tool protocol for `render` and `validate`; `estop`,
  `execute_capability`, and `execute_task` are Python-only for now.

### Added dependencies

- `mcp>=1.0` — MCP SDK (required; server over stdio)
- `anthropic>=0.30` — for `execute_task` with `provider: anthropic`
- Optional extra `robot-md[feetech-depthai]`: `pyserial`, `depthai`,
  `opencv-python`, `numpy`

---

## [0.2.7] - 2026-04-18

Claude Desktop + Claude Mobile support lands. Every surface Anthropic
ships now has a documented, tested install path.

### Added

- **`robot-md install-desktop ROBOT.md`** — merges a `robot-md` entry
  into the OS-appropriate `claude_desktop_config.json` (macOS:
  `~/Library/Application Support/Claude/`, Windows: `%APPDATA%/Claude/`,
  Linux best-effort: `~/.config/Claude/`). Preserves any existing
  `mcpServers` entries. Idempotent re-run. `--force` overrides a
  conflicting existing entry. Claude Desktop launches `npx -y
  robot-md-mcp <absolute path>` on startup via stdio.
- **`integrations/claude-desktop/README.md`** — full install + verify
  + troubleshooting flow. Replaces the outdated "when v0.2 lands"
  draft.
- **`integrations/claude-mobile/README.md`** — URL-fetch pattern.
  Host `ROBOT.md` + `.well-known/robot-md.json` at any public HTTPS
  URL; paste URL into Claude Mobile; Claude fetches + reasons over
  capabilities/safety. The CLAUDE.md auto-generated by init makes the
  safety posture explicit, so mobile operators get the gate-check
  logic without needing `/check-safety` the tool.

### Changed

- **README Claude-integration table** now reflects shipped reality
  instead of "v0.2 coming soon." Every row is ✅ shipped with a
  concrete one-command install.

---

## [0.2.6] - 2026-04-18

### Changed

- **Refreshed bundled `using-robot-md` skill** to reference the MCP
  prompts (slash commands) that ship in `robot-md-mcp` v0.2.1+:
  `/brief-me`, `/check-safety action=<text>`, `/explain-capability
  capability=<name>`, `/manifest-status`. The skill now tells Claude:
  when an operator's intent matches a slash command, mention the
  command exists so the operator can invoke it explicitly next time.
  Upgrade via `pip install --upgrade robot-md && robot-md install-skill --force`.

---

## [0.2.5] - 2026-04-18

Zero-touch agent-path release. Install robot-md → run init → Claude
Code recognizes the robot. No separate commands to learn.

### Added

- **`robot-md init --with-claude-md` (default: on)** — after writing
  `ROBOT.md`, init now also generates a `CLAUDE.md` next to it. Uses
  the same sentinel-wrapped append/update-in-place merge logic from
  0.2.4, so an existing `CLAUDE.md` with operator notes is preserved.
  Opt out with `--no-claude-md`.
- **`robot-md install-skill`** — copies the bundled `using-robot-md`
  skill into `~/.claude/skills/using-robot-md/SKILL.md` (or a custom
  `--dest`). For operators running [superpowers](https://github.com/obra/superpowers)
  or any skill-aware harness, this wires the "Claude auto-invokes
  robot-md when you mention the robot" behavior in one command. Pass
  `--stdout` to preview.
- **Skill bundled in the wheel** at `robot_md/skills/using-robot-md.SKILL.md`.
  Single source of truth: the dev-tree copy at
  `integrations/claude-code-skill/SKILL.md` is kept in sync.

### One-command agent path

The installed + recognized flow is now:

    pip install robot-md && \\
        robot-md init my-bob --preset so-arm101 --register --contact-email me@co.com && \\
        robot-md install-skill && \\
        claude mcp add robot-md -- npx -y robot-md-mcp "$(pwd)/ROBOT.md"

After that, Claude Code routes robot-related questions through the
manifest automatically — no operator mention of robot-md needed.

---

## [0.2.4] - 2026-04-18

### Changed

- **`robot-md claude-md` now preserves existing `CLAUDE.md` content.**
  Old behavior was to refuse writing unless `--force` was passed, which
  destroyed any operator-authored notes. New behavior:
    - File does not exist → write it (with sentinel comments around
      the robot-md block).
    - File exists, has our sentinels → **update the delimited block in
      place.** Operator content above AND below the block is preserved.
    - File exists, no sentinels → **append our block at the end** (with
      sentinels). Operator's original content stays at the top.
    - `--force` → overwrite the entire file (unchanged).
  The sentinel markers are `<!-- BEGIN robot-md ... -->` /
  `<!-- END robot-md -->`; re-running the command multiple times is
  idempotent (file size stabilizes, exactly one delimited region).

---

## [0.2.3] - 2026-04-17

Agent-affordances release — ships tooling explicitly designed for
Claude Code (and any CLAUDE.md-aware agent harness) to recognize when
to dispatch robot-md verbs. Two new verbs, one new discovery standard,
all focused on "let Claude figure out what the operator wants."

### Added

- **`robot-md claude-md ROBOT.md`** — generates a `CLAUDE.md` file
  tailored to a specific robot. The template declares which operator
  intents should trigger which `robot-md` verb (diagnose →
  `doctor`, manifest queries → MCP resources, motion → check HITL
  gates first). Pre-fills robot name, RRN, declared gates, primary
  driver, public resolver. Drop it next to `ROBOT.md` and Claude Code
  reads it at session start.
- **`robot-md publish-discovery ROBOT.md --url <URL>`** — emits a
  `.well-known/robot-md.json` document so MCP clients, crawlers, and
  federated registries can locate a manifest without prior
  configuration. Includes sha256 digest of the served file + derived
  public resolver URL.
- **Spec §6.1** documents the `.well-known/robot-md.json` discovery
  standard.
- **`integrations/claude-code/CLAUDE.md.template`** — canonical
  template consumed by `robot-md claude-md` (and usable directly by
  operators who want to craft their own).

### Note

v0.2.2's CHANGELOG mentioned `publish-discovery`, but the verb
actually shipped after the v0.2.2 tag was cut (commit `8a990e1`).
`pip install robot-md==0.2.2` gets the older code without the verb.
0.2.3 is the first release where `publish-discovery` and
`publish-discovery`-related spec text are both in the package.

---

## [0.2.2] - 2026-04-17

"Proceed with all recommendations" release. Adds a diagnostic verb, five
new presets, a Claude-Code-native onboarding path, and clear labeling of
the terminal vs. in-session on-ramps.

### Added

- **`robot-md doctor`** — diagnostic verb. Runs five buckets of checks
  (install, manifest, network, drivers, keystore) and prints a rich
  table. `--json` for CI, `--strict` to exit non-zero on warnings.
  Read-only: never writes files, never touches servo state.
- **Five new presets**: `franka-panda` (7-DoF Franka FCI arm),
  `ur5e` (6-DoF Universal Robots cobot), `koch-arm` (5+1-DoF LeRobot
  teleop rig, Dynamixel), `aloha2` (bimanual 12-DoF ViperX-300s),
  `unitree-go2` (12-DoF quadruped via Unitree SDK 2). All ship with
  realistic DH params + driver blocks; operators calibrate from there.
- **`docs/getting-started-claude-code.md`** — onboarding walkthrough
  for operators who want Claude Code itself to run the setup. Paste
  one English sentence; Claude uses its `Bash` tool to run the same
  one-liner as the terminal path and wires up MCP afterwards.
- **Two-path getting-started section** in the README and the website.
  The one-liner is now explicitly labeled "▶ On your machine
  (terminal)" and a parallel "▶ Inside Claude Code" card shows the
  prompt-driven flow. SessionStart hook becomes Option C.

### Fixed

- **`bob.ROBOT.md`** `network.rrf_endpoint` was pointing at
  `robotregistryfoundation.org` (the governance site). Updated to
  `https://rcan.dev` so `robot-md doctor` against the example
  resolves correctly.

---

## [0.2.1] - 2026-04-18

One-command-complete-setup release. Patch-bump to land three audit-driven
fixes that turned the v0.2.0 register flow from "4 commands + manual edit
afterwards" into a genuine single-command experience.

### Fixed

- **Register endpoint URL drift** (silent failure in v0.2.0). The CLI
  default was `https://robotregistryfoundation.org/api/v1/robots` — but
  the live registry service runs at `https://rcan.dev/api/v1/robots`
  (the foundation's governance home is at robotregistryfoundation.org;
  the service is hosted separately on rcan.dev). Anyone who ran
  `robot-md register` in v0.2.0 got an HTML response from the marketing
  site back, not a minted RRN. Now points at `rcan.dev`.
- **Manifest/RRF metadata drift.** When `init --register` was called
  with CLI overrides (`--manufacturer`, `--model`, etc.), the override
  was sent to RRF's mint endpoint but the *manifest on disk* kept the
  preset defaults — silently creating a ROBOT.md whose identity fields
  didn't match the RRF entry. Now overrides land in the manifest before
  register runs, so the two stay self-consistent.
- **Preset-generated manifests missing required mint fields.** `preset:
  so-arm101` previously left `metadata.manufacturer/model/version/
  device_id` empty, so `--register` would fail with "missing required
  mint fields" until the operator hand-edited the file. Now the preset
  seeds defaults: manufacturer=device_id=robot_name, model=preset_name,
  version="1.0". Operator overrides win.

### Added

- **`robot-md init --register [--contact-email ... --manufacturer ...
  --model ... --version- ... --device-id ...]`** — one-command complete
  setup. Validates + POSTs to rcan.dev + updates the manifest with the
  assigned RRN + prints the `claude mcp add` line. No other commands
  needed. No OpenCastor. Live-verified end-to-end: `RRN-000000000006`
  minted, manifest + RRF entry consistent, MCP server streams the 4
  resources cleanly. (Test entry cleaned up via new `unregister` verb.)
- **`robot-md unregister <RRN> [--api-key PATH]`** — DELETEs an RRF
  entry using the issued API key (reads from
  `~/.robot-md/keys/<rrn>.apikey` by default). Removes the local key
  file after a successful delete. Does not touch local ROBOT.md files.

### Examples updated

- `examples/bob.ROBOT.md` now reflects the live Bob entry on rcan.dev:
  RRN-000000000003 (minted 2026-04-15), manufacturer=craigm26,
  model=opencastor-rpi5-hailo-soarm101, version=1.0, device_id=bob-001.
  Verify live: https://rcan.dev/r/RRN-000000000003

## [0.2.0] - 2026-04-18

Big release. `robot-md` goes from "validator for a file format" to
"operator toolkit" — one command takes a new user from plugged-in
hardware to a manifest Claude Code can ingest, with physical calibration
and RRF identity minted in the loop.

### Added

- **`robot-md init [NAME] [--preset NAME] [--wizard]`** — super-duper-quick
  zero-to-ROBOT.md. Default mode emits a validated draft in one shot by
  matching a preset from the built-in library; `--wizard` opens a 7-step
  interactive flow for custom hardware. `--list-presets` prints the
  library.
- **Preset library** at `cli/src/robot_md/presets/` — 5 shipped:
  `so_arm101`, `so_arm101_leader`, `turtlebot4`, `picar_x`, `minimal`.
  YAML (not code) so community preset PRs stay low-friction.
- **`robot-md calibrate --zero`** — operator poses arm in declared zero
  configuration, CLI reads every joint's Present Position, rewrites
  `physics.kinematics[].zero_pose_steps` in place (ruamel.yaml
  preserves comments).
- **`robot-md calibrate --sign`** — per-joint test move, operator
  confirms direction, `encoder_sign` written.
- **`robot-md calibrate --hand-eye --marker-pos X,Y,Z`** — ArUco +
  `cv2.solvePnP` camera-to-arm-base extrinsic. Writes
  `physics.solver.camera.extrinsic` as `[tx, ty, tz, rx, ry, rz]` (mm +
  Rodrigues radians). OAK-D intrinsics pulled via
  `depthai.Device.readCalibration()` — no external calibration file.
- **`robot-md register`** — POSTs manifest metadata to RRF's mint
  endpoint (`https://robotregistryfoundation.org/api/v1/robots`). Writes
  the assigned RRN back into `metadata.rrn`, stores the one-time API
  key at `~/.robot-md/keys/<rrn>.apikey` (mode 600). `--dry-run` and
  `--endpoint` override supported.
- **`robot-md autodetect --bus feetech:<port>[:<baud>]`** — Tier B
  servo-bus scan. Pings IDs 1..253 (3 retries × 20 ms); reads min/max
  angle limits + present position; emits a populated
  `physics.kinematics[]` block with `joint_<N>` placeholders.
- **Baseline `Kinematics` module** (`robot_md.kinematics`) — reads
  `physics.solver` + `physics.kinematics[]` and provides FK / 3-link
  planar IK / encoder-step ↔ joint-angle conversions. Any planner with
  just a validated ROBOT.md can reach a pose from the manifest alone —
  no URDF, no MoveIt.
- **v1.1 schema additions**:
  - `physics.solver.{convention, base_frame, encoder, camera, gripper}`.
  - Per-joint `servo_id`, `encoder_sign`, `zero_pose_steps`, `a_mm`,
    `d_mm` (DH params).
  - All backwards-compatible: 0.1.x manifests validate unchanged.
- **Tier A autodetect polish**:
  - `DRIVER_PROFILES` table — autodetect now pre-fills
    `drivers[].baud_rate` from protocol (Feetech bus → 1 Mbps etc.).
  - `probe_cameras()` — OAK-D via DepthAI + v4l2-ctl enumeration.
    Emits a `cameras:` block when real cameras are found; filters Pi
    ISP plumbing (bcm2835-isp/codec, pispbe, rpi-hevc-dec).
- **RCAN 3.0+ + RRF-aware generated manifests.** `init` writes a
  default `network` block with `rrf_endpoint`,
  `signing_alg: ml-dsa-65`, `transports: [http]`.
- **Spec `autodetect-prefill-roadmap.md`** maps which fields are
  auto-fillable at what tier (host scan / bus scan / preset) and where
  operator walk-through takes over.

### Changed

- `examples/bob.ROBOT.md` carries the full solver block + DH params +
  `/dev/ttyACM0` port + `tip_offset_mm: [30, 0, 0]`.
- Core deps: `ruamel.yaml>=0.18`, `numpy>=1.24`. New optional extras:
  `feetech` (servo SDK) and `vision` (opencv-contrib-python + depthai).
- CLI help output rewritten with examples for every new command.

### Fixed

- Schema-sync CI gate — canonical, CLI-bundled, and site-served
  `robot.schema.json` copies must all match.

### Tests

Suite grows 59 → 127 passing. New test files: `test_kinematics.py`,
`test_calibrate.py`, `test_autodetect_tier_a.py`, `test_bus_scan.py`,
`test_init.py`, `test_register.py`, `test_hand_eye.py`.

## [0.1.3] - 2026-04-17

### Added

- **Autodetect hardware DB expansion.** Eight additional device families,
  each tagged with provenance in-source and covered by synthetic-fixture
  tests:
  - **Cameras:** Intel RealSense D435i, D455, L515; Stereolabs ZED 2.
  - **MCUs:** Arduino Uno R1/R3, Arduino Mega 2560, Arduino Leonardo,
    Raspberry Pi RP2040 (including BOOTSEL), PJRC Teensy.
  - **Motor control:** ODrive V3 BLDC controller.
- Introduces two new device roles in the autodetect schema: `mcu` and
  `motor-controller`. Existing `npu`, `camera`, `serial-bus`, and
  `serial-port` roles unchanged.

### Internal

- Test suite expanded from 13 → 17 autodetect cases; total CLI suite now
  59 tests.

## [0.1.2] - 2026-04-17

### Added

- **`robot-md autodetect`** — scan visible hardware and emit a draft
  `ROBOT.md`. Detects Hailo-8 / Hailo-10H (PCI), Intel Movidius NCS 1/2 (USB),
  Luxonis OAK-D (USB), Google Coral USB Accelerator (USB), Intel RealSense
  D435 (USB), and common USB-serial bridges (CH340, CH341, CP210x, FTDI
  FT232R). Also probes `/dev/ttyACM*` / `/dev/ttyUSB*` and common
  robot-stack tools (`claude`, `opencastor`, `castor`, `rcan-validate`,
  `hailortcli`, `i2cdetect`). Linux-only in this release.
  - Default emits draft to stdout. `--write PATH` writes to a file and
    refuses to overwrite.
  - Emitted draft uses `"CHANGE-ME"` / `"other"` placeholders for identity
    fields and schema-validates — but will not claim to know actuator count
    or physics type without operator review.
  - Hardware DB lives in `robot_md/autodetect.py` with VID:PID provenance
    comments on every entry. PRs to extend it are welcome.
- **v0.2 design document** at `spec/v0.2-design.md` (published at
  `robotmd.dev/spec/v0.2-design.md`): signing, registry ingestion, and
  tamper-evidence plan. Design-only; no code. Evaluates blockchain
  options and recommends centralized D1 baseline for v0.2 (cheapest,
  simplest) with Merkle transparency log as a documented v0.3+ upgrade
  path. §13 collects four Decision Required items gating implementation.

### Changed

- README: added v0.2 design link to Spec + docs. Removed broken
  proposal link (outreach materials live in the private repo).

## [0.1.1] - 2026-04-17

### Fixed

- **`robot-md validate` could not find the JSON schema when installed as a wheel.** `validate.py` computed `_SCHEMA_PATH` relative to `__file__` using a four-level `parent` walk that only resolved correctly in the source tree — once `pip install`'d, the path pointed outside `site-packages` and every `validate` call raised `FileNotFoundError`. Fixed by bundling `schema/v1/robot.schema.json` as a package resource under `robot_md/schemas/v1/` and loading it via `importlib.resources.files()`. Canonical schema source remains `schema/v1/robot.schema.json` at the repo root; `scripts/sync-schema.sh` keeps the bundled copy in sync.
- **`robotmd.dev/schema/v1/robot.schema.json` was serving the landing page HTML** instead of the schema (same for `/examples/*`, `/hook`, and `/spec/v1`). Cloudflare Pages SPA-falls-back to `index.html` for missing paths, making the 404 invisible. Added the canonical assets under `site/` so Pages deploys them, with `Content-Type` rules in `_headers` so the schema serves as `application/schema+json`, examples and spec as `text/markdown`, and `/hook` as `text/x-shellscript`. All gain `Access-Control-Allow-Origin: *` for cross-origin validators.

### Security

- Tightened schema bounds on physical-safety fields so manifests claiming absurd values (unbounded velocity, 10-tonne payloads, 10-second E-stop response) are rejected at validation. Full hardened bounds in `SECURITY.md`. Existing examples (Bob, SO-ARM101, minimal, TurtleBot 4) all still validate.
- Added new optional declarative fields: `safety.workspace_bounds_m` (spatial envelope) and `safety.failsafe_behavior` (`stop` / `hold` / `home` / `custom` — planner's mandated behavior on comms loss).
- Added **"Known v0.1 Limitations"** section to `SECURITY.md` documenting gaps in physical safety (manifest is declarative, not enforcing), digital security (no signing yet — planned v0.2), and registry integration (no RRF-side manifest ingestion yet — planned v0.2). Includes the Tier 0 threat model: **"trusted operator + trusted planner"** only; do not expose a Tier 0 robot to untrusted prompts without a gateway layer.

### Changed

- Repo migrated to the **Robot Registry Foundation** GitHub org (`github.com/RobotRegistryFoundation/robot-md`). Old URL 301-redirects indefinitely. Cloudflare Pages secrets + the `production` and `pypi` GitHub environments were preserved through the transfer; no downstream action required from consumers.
- Dogfood `ROBOT.md` `metadata.manufacturer` updated from `craigm26` to `RobotRegistryFoundation` to match the new steward.

## [0.1.0] - 2026-04-17

### Added

Initial v0.1 release.

- `ROBOT.md` format specification (`spec/robot-md-v1.md`)
- JSON Schema for the frontmatter block (`schema/v1/robot.schema.json`)
- Python CLI `robot-md` with subcommands:
  - `robot-md validate PATH` — schema + RCAN 3.0 conformance check
  - `robot-md render PATH` — strip prose, emit pure YAML
  - `robot-md context PATH` — emit Claude-ready text block
- Four worked examples: `bob.ROBOT.md`, `minimal.ROBOT.md`, `so-arm101.ROBOT.md`, `turtlebot4.ROBOT.md`
- Claude Code SessionStart hook (`integrations/claude-code/session-start.sh`)
- Documented MCP + URL-bridge approaches for Claude Desktop and Mobile
- Draft Anthropic adoption proposal

### Not yet

- `robot-md register` (RRF integration) — planned for v0.2
- Working MCP server for Claude Desktop — planned for v0.2
- URL bridge Cloudflare Worker for Claude Mobile — planned for v0.2
- TypeScript port (`@robotmd/spec`) — planned for v0.2
