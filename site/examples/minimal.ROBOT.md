---
rcan_version: "3.0"
metadata:
  robot_name: minimal
physics:
  type: wheeled
  dof: 2
drivers:
  - id: wheels
    protocol: pca9685
safety:
  estop:
    software: true
    response_ms: 200
---

# minimal

## Identity

The smallest valid `ROBOT.md`. Every field present here is required; nothing else is set. Use this as the starting point for a new robot.

## What minimal Can Do

Nothing yet — this file has no `capabilities` declared. Add a `capabilities:` block to the frontmatter and document the skills below to bring the robot online.

## Safety Gates

Software E-stop only; response time is 200 ms. No hardware E-stop on this reference robot. Add `hitl_gates` when the robot starts exposing skills that can cause real-world change.
