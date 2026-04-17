---
rcan_version: "3.0"
metadata:
  robot_name: turtlebot4
  manufacturer: clearpath
  model: turtlebot4-lite
  license: Apache-2.0

physics:
  type: wheeled
  dof: 2

drivers:
  - id: base
    protocol: ros2
    model: turtlebot4
  - id: lidar
    protocol: lidar
    model: rplidar-a1
  - id: camera
    protocol: picamera2

brain:
  planning:
    provider: anthropic
    model: claude-sonnet-4-6
    confidence_gate: 0.55
  task_routing:
    sensor_poll: fast_only
    safety: planner_always
    navigation: planner

capabilities:
  - nav.go_to
  - nav.stop
  - vision.describe
  - status.report

safety:
  p66_enabled: true
  loa_enforcement: true
  max_linear_velocity_ms: 0.5
  estop:
    hardware: true
    software: true
    response_ms: 150
  hitl_gates:
    - scope: destructive
      require_auth: true

network:
  port: 8002
  signing_alg: pqc-hybrid-v1
  transports: [http]
---

# turtlebot4

## Identity

A Clearpath TurtleBot 4 Lite running OpenCastor over ROS 2. Two-wheeled differential drive, RPLIDAR A1 at the front, PiCamera 2 on top. Controlled via Claude Sonnet 4.6 (the smaller model — TurtleBot tasks rarely need the full Opus planner).

## What turtlebot4 Can Do

- **Navigate** (`nav.go_to`, `nav.stop`) — autonomous point-to-point movement within the known map. Obstacle avoidance via LIDAR.
- **See** (`vision.describe`) — captions of the front camera view.
- **Status** — battery, motor health, LIDAR health, localization confidence.

## Safety Gates

1. Hardware E-stop button on the top deck. Software E-stop at 150 ms response. Either triggers immediate halt.
2. Max linear velocity 0.5 m/s. The chassis CAN go faster but not safely in indoor human-occupied spaces.
3. `destructive` scope (e.g., ramming a closed door to test "navigation failure recovery") requires HITL auth. Don't.
4. LIDAR health degradation > 20% fault rate triggers automatic halt until operator acknowledges.
