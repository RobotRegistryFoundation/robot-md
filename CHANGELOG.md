# Changelog

All notable changes to `robot-md` are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
