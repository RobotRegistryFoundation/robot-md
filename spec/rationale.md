# ROBOT.md — Rationale

## Why one file?

Robotics deployments today split the robot's self-description across: a YAML config for the runtime, a P66 manifest for safety, a CLAUDE.md for the planner, a firmware manifest for attestation, and often a README for humans. Every file drifts against the others. When a new joint is added, three files need to update.

`ROBOT.md` is the single source of truth. The runtime reads the frontmatter; the planner reads the full file; validators read the schema. Drift becomes a schema violation, not a latent bug.

## Why frontmatter + prose?

Frontmatter is machine-editable, indexable, and enforceable. Prose is LLM-editable, explainable, and reviewable. Neither alone is sufficient:

- YAML-only: the planner doesn't know *why* `max_joint_velocity_dps: 180` — is this a safety bound or a motor limit? Context matters.
- Prose-only: safety checks can't verify that the declared payload is ≤ the configured HITL gate threshold.

The frontmatter IS the contract. The prose IS the explanation. Both are required.

## Why parallel `CLAUDE.md`?

Claude Code users already know how `CLAUDE.md` works: drop it in the repo root, Claude reads it at session start, now the planner has context. `ROBOT.md` reuses this exact mental model for physical robots. Zero learning curve.

## Why not extend `CLAUDE.md` to cover robots?

Two reasons:

1. **Separation of concerns**: a robot may live inside a repo (a codebase-oriented `CLAUDE.md`) or on its own (a deployment-oriented `ROBOT.md`). Conflating them forces one file to do two jobs.
2. **Surface portability**: `CLAUDE.md` is a Claude Code convention. `ROBOT.md` is intended for any Claude surface (Code, Desktop, Mobile), and ideally for non-Claude planners too. A distinct name signals distinct semantics.

## Why require RCAN 3.0+ baseline?

RCAN 3.0 added the compliance blocks (EU AI Act, FRIA, post-market monitoring) that make a robot deployable under regulatory scrutiny. A ROBOT.md at RCAN 2.2 or below can't express these — and shipping a robot in the EU without them is increasingly illegal. Forcing 3.0+ means every ROBOT.md is regulator-ready by construction.

## Why `pqc-hybrid-v1` as default signing?

Ed25519 is deprecated by NIST for long-lived key material. RCAN 3.0 §9 rejects Ed25519-only profiles at L2+. Defaulting to `pqc-hybrid-v1` means a robot declared via ROBOT.md is future-proof under the new signing requirements without the operator having to remember to upgrade.

## Why optional `brain`?

Not every robot has an LLM planner. A battery monitor, a weather station, a security camera — these are robots (or robot-like sensor nodes) with capabilities but no planning layer. The `brain` block is required ONLY when the robot is expected to host a Claude session.

## Why defer `robot-md register` to v0.2?

Minimizing v0.1 dependencies. The core validator only needs frontmatter parsing + JSON Schema + YAML — no HTTP. Adding `httpx` for `register` means another pinned version and another surface to break. v0.1 is pure-Python, pure-sync, no network. v0.2 adds `register` with the smallest HTTP surface possible.

## Driver protocol list

Recognized `drivers[].protocol` values match `castor.drivers.<name>` in OpenCastor:

`pca9685`, `dynamixel`, `feetech`, `gpio`, `arduino`, `esp32-ble`, `esp32-websocket`, `odrive`, `can`, `ros2`, `stepper`, `imu`, `lidar`, `thermal`, `battery`, `picamera2`, `acb`, `ev3dev`, `spike`, `reachy`, `depthai`, `simulation`, `composite`.

Unknown protocols MAY appear — the schema warns but doesn't fail (vendors extend via `extensions.x-<vendor>`).

## Unresolved questions (v1 → v2 candidates)

- Should `capabilities[]` be objects with params (e.g., `{name: arm.pick, params: [object_id]}`) instead of bare strings?
- Should `safety.hitl_gates` be unified with RCAN's authorization block (`§8`)?
- Should there be a `telemetry:` block for declaring what the robot publishes upstream?

These are intentionally left for v2. v1 ships the minimum viable surface.
