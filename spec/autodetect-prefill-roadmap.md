# ROBOT.md autodetect pre-fill roadmap

> **Status:** design doc. Tracks what `robot-md autodetect` + friends can
> populate today, what they could with targeted enhancements, and where
> operator walk-through takes over. v1.0 (date-stamped 2026-04-17).

## The question this answers

> How much of a ROBOT.md can we pre-fill for the operator, and which
> fields inherently require human discretion or physical calibration?

The stance: minimize operator effort for deterministic data, be explicit
about what can't be automated, and provide a clean walk-through that
hands off between the two. "Some operator discretion + calibration for
any device is OK" — we don't need 100% autonomy; we need the boundary
to be clear.

---

## Tiers of pre-fillability

### Tier A — Deterministic from a host-side scan *(no robot required)*

What the host already knows. `robot-md autodetect` covers most of this
today; a few gaps worth closing.

| Field | Source | Status |
|---|---|---|
| `drivers[].protocol` | PCI/USB vendor:product tables | ✓ shipped |
| `drivers[].port` | `/dev/tty*` enumeration | ✓ shipped |
| `drivers[].model` | USB string descriptor + vendor table | ✓ shipped |
| `drivers[].baud_rate` | Protocol defaults (Feetech 1 Mbps, Dynamixel 57.6–4 M) | ⚠ partial |
| `drivers[].count` | USB enumeration count | ✓ shipped |
| `physics.solver.encoder.steps_per_rev` | Driver-type → fixed value (Feetech STS3215 = 4096) | ✗ missing |
| Bundled hardware notes | PCI/USB IDs as markdown comments | ✓ shipped |
| `cameras[].type`, `.model` | `depthai.Device.getConnectedCameraFeatures()` / v4l2 probe | ✗ missing |
| `cameras[].resolution`, `.fps` | Same | ✗ missing |

**Gap closure:** add a driver-type table that emits `steps_per_rev`,
default `baud`, and the common "protocol 0 vs 2" flag for SCServo-family
buses. Add a depthai/v4l2 camera probe to `autodetect.scan_system()`.

### Tier B — Bus introspection *(robot plugged in, not necessarily powered-on arm)*

For servo buses that expose their own address + configuration via the
wire protocol, we can walk the bus and read per-servo registers.

| Field | How | Notes |
|---|---|---|
| `kinematics[].servo_id` | Feetech: ping IDs 1..253, collect responders | Cheap, ~1 s scan |
| `kinematics[].limits_deg` | Feetech: read `Min Angle Limit` (0x09) + `Max Angle Limit` (0x0B) | Servo-side config often wrong by default; still a useful floor |
| `kinematics[].zero_pose_steps` *(candidate)* | Read `Present Position` (0x38) at scan time | Only a *default* — operator still runs `calibrate --zero` later |
| Current-draw / temperature / fault-flags | Multiple registers | Optional — useful for health-check `drivers[].health_policy` |

**Proposal:** `robot-md autodetect --bus feetech:/dev/ttyACM0` scans the
bus, populates `kinematics[]` with servo_id-indexed entries named
`joint_1`, `joint_2`, …, populates limits and initial position. Operator
renames joints to real names + fills the rest.

### Tier C — Preset library *(known model, skip most manual work)*

For robots that are off-the-shelf units with public geometry
(SO-ARM101, TurtleBot 4, Unitree Go2, Reachy, etc.), we can ship a
one-line `--preset` flag that unions the preset's kinematic chain into
the generated draft.

Proposed layout:

```
cli/src/robot_md/presets/
  so_arm101.yaml       # 6-DoF follower arm (Feetech × 6)
  so_arm101_leader.yaml
  turtlebot4.yaml       # differential-drive base + LIDAR + camera
  unitree_go2.yaml      # quadruped
  reachy_mini.yaml
  picar_x.yaml
  ...
```

Each preset declares:

- `physics.type` and `dof`
- Full `physics.kinematics[]` with `a_mm`, `d_mm`, `axis`, `limits_deg`,
  joint names, and `encoder_sign` hints (with a note: "verify via
  `calibrate --sign`")
- `physics.solver.gripper` — if applicable, with `tip_offset_mm` and
  `open_steps` / `close_steps` populated from the manufacturer's spec
- Default `safety` block — payload, max joint velocity, workspace bounds
- Common `capabilities` for the class (arm presets include `arm.pick`,
  `arm.place`, etc.)

What operators still fill in per-deployment:

- `metadata.robot_name`
- `metadata.rrn` (until v0.2 auto-register)
- Any deployment-specific safety tightening (reduced payload, HITL gates)
- Prose body

**Command:**

```bash
robot-md autodetect --preset so-arm101 --write ROBOT.md
# → draft combines hardware scan + SO-ARM101 kinematics + sensible defaults
# → TODO markers on robot_name + rrn
# → ready for validate, then calibrate --zero + --sign
```

### Tier D — Operator discretion and physical calibration

These fields **cannot** be safely autodetected. The manifest should
explicitly flag them as operator-supplied.

| Field | Why not automatic |
|---|---|
| `metadata.robot_name` | Identity choice |
| `physics.type` | Ambiguous for novel / composite machines |
| `kinematics[].encoder_sign` | Requires commanded test move + visual confirmation (`calibrate --sign`) |
| `kinematics[].zero_pose_steps` (authoritative) | Requires operator to hold arm at declared zero pose (`calibrate --zero`) |
| `solver.camera.extrinsic` | Hand-eye calibration run (`calibrate --hand-eye`, ArUco-based) |
| `safety.payload_kg` | Depends on what the operator plans to lift |
| `safety.hitl_gates[]` | Reflects the deployment's consent / authority model |
| `compliance.fria_ref`, `.eu_register` | Legal / organizational filings |

---

## The operator walk-through — `robot-md init`

Proposed new CLI verb that ties everything together into one
conversational flow. The target: an operator with a freshly-plugged-in
SO-ARM101 + OAK-D + Pi 5 gets to "Claude Code knows this robot" in
~5 minutes.

```
$ robot-md init
Welcome. Let's create a ROBOT.md.

[1/7] Robot name? (short, lowercase) > bob
[2/7] Physics type? (arm / wheeled / legged / humanoid / sensor / other) > arm
[3/7] Known preset? (so-arm101 / turtlebot4 / unitree-go2 / custom) > so-arm101

  Scanning hardware...
    ✓ Feetech bus on /dev/ttyACM0 — 6 servos (IDs 1..6)
    ✓ OAK-D camera detected (1920×1080 @ 30fps)
    ✓ Hailo-8 NPU present

[4/7] Write draft to ./ROBOT.md? (y/n) > y
  ✓ wrote ROBOT.md

[5/7] Calibrate zero pose now? You'll need to physically hold the
      arm in the reference configuration. (y/n) > y
  > Pose the arm straight out along +x with gripper forward, then Enter.
  > [Enter]
  ✓ recorded zero_pose_steps for 6 joints

[6/7] Calibrate encoder signs now? I'll command +100 steps on each
      joint and ask which way it moved. (y/n) > y
  > Testing shoulder_pan... which way did it move?
      (a) left-when-viewed-from-above  (b) right-when-viewed-from-above
  > a
    ...
  ✓ recorded encoder_sign for 6 joints

[7/7] Hand-eye calibration? Requires a printed ArUco marker. (y/n) > n
  Skipped — run `robot-md calibrate --hand-eye` later.

✓ Done. Next:
    robot-md validate ROBOT.md
    claude mcp add robot-md -- npx -y robot-md-mcp "$(pwd)/ROBOT.md"
```

This is the "dead-simple setup" the marketing doc promises, made real.

---

## Roadmap — concrete tasks

Numbered for tracking; each becomes a task in the project board.

1. **Driver type table for Tier A completion.** Map protocol → `{steps_per_rev, default_baud, protocol_version}`. Populate in `physics.solver.encoder` during autodetect.
2. **Camera probe.** Add depthai/v4l2 enumeration to `scan_system()`. Emit `cameras[]` block with `model`, `resolution`, `fps`.
3. **Feetech bus scan.** New `--bus feetech:<port>` flag. Pings IDs 1..253, reads limits, writes `kinematics[]` with placeholder joint names.
4. **Preset library.** Ship `presets/so_arm101.yaml`, `presets/so_arm101_leader.yaml`, `presets/turtlebot4.yaml`, `presets/minimal.yaml`. `--preset <name>` unions the preset with the hardware scan.
5. **`robot-md init` wizard.** Interactive 7-step walkthrough combining autodetect + preset + calibrate. Default entry point for new users.
6. **`calibrate --sign`** (follow-up to task #44). Commands +N steps per joint, asks operator for observed direction, sets `encoder_sign`.
7. **`calibrate --hand-eye`** (follow-up to task #44). Uses OAK-D + ArUco marker on gripper to solve extrinsic. Writes `solver.camera.extrinsic`.
8. **v0.2 `robot-md register`** (task #19's real successor). Posts signed manifest to RRF, binds key → RRN at mint time, writes assigned RRN back into manifest. Blocked on v0.2 signing sign-off (see `spec/v0.2-design.md`).

After all 8 land, a fresh Pi-5-plus-SO-ARM101 operator has a complete,
calibrated, registered ROBOT.md at the end of one `robot-md init`
session. That's the north star.

---

## Design principles

1. **Pre-fill is opt-in per tier.** `autodetect` does Tier A by default;
   `--bus` adds Tier B; `--preset` adds Tier C; `init` composes all of
   the above.
2. **Never silently guess Tier D fields.** If `encoder_sign` isn't
   calibrated, the draft emits `# TODO: run \`robot-md calibrate --sign\``
   rather than a default. Operators should see the gap, not trip over it.
3. **Presets are YAML, not code.** A community-contributable `presets/`
   directory keeps the library growing without CLI churn.
4. **Every autodetected field is marked with its provenance.** A YAML
   comment tag like `# (autodetected from PCI 1e60:2864)` helps the
   operator know what to trust vs. verify.
5. **The wizard never blocks on optional steps.** Hand-eye calibration
   is valuable but not required for first-light use. Steps 6–7 must be
   skippable.

---

## Non-goals

- 6-DoF IK for arbitrary arm topologies. The baseline solver already
  shipped in v1.1 covers SO-ARM101-style chains; general IK remains
  a "bring ikpy / MoveIt" story.
- URDF parsing. We respect the `convention: URDF` escape hatch but
  don't build a URDF → ROBOT.md importer here. That's a separate
  tool if it's ever worth shipping.
- Self-healing calibration. If the arm gets bumped, the manifest
  doesn't detect it — the operator re-runs `calibrate --zero`.
  Post-bump auto-detection is a research problem, not a v1.1 goal.

---

## Open questions for review

1. Should presets be bundled with the CLI (`cli/src/robot_md/presets/`)
   or shipped as a separate package (`robot-md-presets` on PyPI)?
   Bundling is simpler for first users; separation makes community
   contribution lower-friction. Proposal: bundle for v1.1, split only
   if the preset library grows past ~20 robots.

2. For the bus scan, do we accept that some servos won't respond on
   first ping (power sag, bus collision) and retry, or treat a silent
   ID as absent? Proposal: 3 retries with 20 ms backoff, mark absent
   after that.

3. `robot-md init` wants a persistent state file so a half-finished
   session can be resumed. Where? Proposal: `./ROBOT.md.init` next
   to the manifest, auto-deleted on successful completion.

4. Do we want `autodetect --output json` for machine-readable
   consumption by other tools (e.g. a GUI setup wizard)? Proposal: yes,
   file as low-priority.
