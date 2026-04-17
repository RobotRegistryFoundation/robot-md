---
rcan_version: "3.0"
metadata:
  robot_name: no-id
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

# no-id

## What no-id Can Do
Missing Identity section.

## Safety Gates
Present.
