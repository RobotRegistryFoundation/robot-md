---
rcan_version: "3.0"
metadata:
  robot_name: test-bot
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

# test-bot

## Identity
Minimal test robot.

## What test-bot Can Do
Move forward.

## Safety Gates
Software E-stop at 200ms.
