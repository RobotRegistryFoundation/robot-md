---
rcan_version: "3.0"
schema: https://robotmd.dev/schema/v1/robot.schema.json

metadata:
  # Identity — both registered + resolvable at rcan.dev.
  # Verify live: https://rcan.dev/r/RRN-000000000003
  robot_name: bob
  manufacturer: craigm26
  model: opencastor-rpi5-hailo-soarm101
  version: "1.0"                            # the registered major.minor — see rcan.dev/r/RRN-000000000003
  device_id: bob-001
  rrn: RRN-000000000003                     # minted 2026-04-15 via `robot-md register`
  rrn_uri: rrn://craigm26/robot/opencastor-rpi5-hailo-soarm101/bob-001
  rcan_uri: rcan://rcan.dev/craigm26/opencastor-rpi5-hailo-soarm101/1-0/bob-001
  ruri: rcan://robot.local:8001/bob         # operator's LAN gateway (RCAN transport)
  license: Apache-2.0
  author: craigm26@gmail.com

physics:
  type: arm+camera
  dof: 6
  solver:
    convention: DH
    base_frame: { up: z, forward: x }
    encoder:
      steps_per_rev: 4096        # Feetech STS3215 native resolution
    camera:
      mount: world               # eye-to-hand; fixed OAK-D looking at the arm's workspace
      extrinsic: null            # run `robot-md calibrate --hand-eye` to populate
    gripper:
      joint_id: gripper
      tip_offset_mm: [30, 0, 0]  # 30mm along tool +x — when wrist rotates tool to
                                 # point down, this becomes 30mm below gripper joint.
                                 # Tool-frame convention: +x = forward at zero pose.
      open_steps: 1700
      close_steps: 1200
  kinematics:
    # DH params: a_mm = horizontal offset to next joint; d_mm = offset along this
    # joint's rotation axis. shoulder_pan is a vertical riser (d=60, a=0); the
    # rest are horizontal links (a>0, d=0). length_mm kept for backward compat.
    - id: shoulder_pan
      axis: z
      limits_deg: [-180, 180]
      length_mm: 60              # legacy — equals d_mm here
      a_mm: 0
      d_mm: 60                   # vertical riser from base to shoulder_lift joint
      servo_id: 1
      encoder_sign: 1            # +Δ encoder ⇒ +Δ angle (CCW from above); confirmed 2026-04-17
      zero_pose_steps: 2048      # midpoint placeholder; replace via `robot-md calibrate --zero`
    - id: shoulder_lift
      axis: y
      limits_deg: [-90, 90]
      length_mm: 125
      a_mm: 125
      d_mm: 0
      servo_id: 2
      encoder_sign: 1            # +Δ ⇒ arm rotates forward/down; confirmed 2026-04-17
      zero_pose_steps: 2048
    - id: elbow_flex
      axis: y
      limits_deg: [-90, 90]
      length_mm: 125
      a_mm: 125
      d_mm: 0
      servo_id: 3
      encoder_sign: 1            # +Δ ⇒ forearm extends; confirmed 2026-04-17
      zero_pose_steps: 2048
    - id: wrist_flex
      axis: y
      limits_deg: [-90, 90]
      length_mm: 60
      a_mm: 60
      d_mm: 0
      servo_id: 4
      encoder_sign: 1            # tentative; calibrate before trusting
      zero_pose_steps: 2048
    - id: wrist_roll
      axis: x
      limits_deg: [-180, 180]
      length_mm: 30
      a_mm: 30
      d_mm: 0
      servo_id: 5
      encoder_sign: 1
      zero_pose_steps: 2048
    - id: gripper
      axis: y
      limits_deg: [0, 90]
      length_mm: 40
      a_mm: 0                    # gripper is passive in FK; tip offset lives in solver.gripper
      d_mm: 0
      servo_id: 6
      encoder_sign: 1
      zero_pose_steps: 1200      # close position; open = 1700

drivers:
  - id: arm_servos
    protocol: feetech
    port: /dev/ttyACM0
    baud_rate: 1000000
    model: STS3215
    count: 6
  - id: camera
    protocol: depthai
    model: OAK-D

brain:
  planning:
    provider: anthropic
    model: claude-opus-4-7
    confidence_gate: 0.60
  task_routing:
    sensor_poll: fast_only
    safety: planner_always
    navigation: planner
    reasoning: planner
    vision: planner
    code: planner

capabilities:
  - arm.pick
  - arm.place
  - arm.reach
  - vision.describe
  - status.report

safety:
  p66_enabled: true
  loa_enforcement: true
  max_joint_velocity_dps: 180
  payload_kg: 0.5
  estop:
    hardware: false
    software: true
    response_ms: 100
  hitl_gates:
    - scope: destructive
      require_auth: true
    - scope: system
      require_auth: true

network:
  rrf_endpoint: https://rcan.dev
  port: 8001
  signing_alg: pqc-hybrid-v1
  transports: [http, mqtt]

compliance:
  fria_ref: null
  iso_42001:
    self_assessed: true
    level: 5
  eu_ai_act:
    audit_retention_days: 3650
---

# bob

## Identity

Bob is a Raspberry Pi 5 (16GB) workstation-class robot with a 6-DOF SO-ARM101 follower arm and a Luxonis OAK-D stereo camera. He lives at `robot.local` on the user's home network. RRN `RRN-000000000003`, registered with the Robot Registry Foundation.

Bob is the reference implementation for the OpenCastor runtime and the first production deployment of the ROBOT.md format. He runs Claude Opus 4.7 as his primary planning brain, relying on local deterministic controllers for low-latency safety tasks.

## What bob Can Do

- **Manipulate** — pick and place payloads up to 0.5 kg. The gripper is joint 6; servo IDs run 1-6 left-to-right along the arm. Inverse kinematics is handled by the OpenCastor runtime.
- **See** — the OAK-D produces RGB + depth. `vision.describe` returns a caption + depth-annotated bounding boxes. `vision.detect` takes a class name and returns bounding boxes + distances.
- **Report status** — health check across all 6 servos + camera + battery + compute temperature.

Bob is stationary — there is no `nav.go_to` capability. Reach is arm-based only (workspace roughly 60 cm radius).

## Safety Gates

1. **Every arm motion routes through `SafetyLayer`.** Joint limits are enforced per-joint via `castor.safety.bounds.BoundsChecker`; motion commands exceeding the configured envelope are rejected before reaching the servo bus.
2. **Destructive actions require human-in-the-loop approval.** `arm.place` onto an unknown surface, `arm.pick` of an object Bob can't identify, and any `system.*` call pause for explicit operator approval via the RCAN `AUTHORIZE` flow (§8).
3. **`sensor_poll` tasks never escalate to the planner.** Token-budget guard — if a sensor poll takes more than 500 ms or requires reasoning, the call returns an error rather than consuming planner tokens.
4. **`safety` tasks always use the planner, never the reactive brain.** E-stop, bounds checks, and override commands must be evaluated by Claude Opus, not OpenVLA.

## Task Routing

The planning brain handles: reasoning, safety arbitration, vision captioning, code generation, and navigation planning. Local deterministic controllers handle: low-latency sensor polling, servo watchdog, and immediate-stop triggers. See `brain.task_routing` in the frontmatter for the exact per-category mapping.

## Extension Points

- **New skills**: register in OpenCastor's `SkillRegistry` at `castor/rcan/invoke.py`, then add the name to `capabilities[]` in this file.
- **New drivers**: add to `drivers[]`; the gateway auto-discovers drivers by `protocol` field on startup.
- **Task-routing overrides**: edit `brain.task_routing`. See the RCAN spec §16 for the full category list.

## References

- RCAN spec: <https://rcan.dev/spec/>
- Robot Registry Foundation: <https://robotregistryfoundation.org/>
- OpenCastor runtime: <https://github.com/craigm26/OpenCastor>
- Bob's public RRF entry: <https://rcan.dev/r/RRN-000000000003>
