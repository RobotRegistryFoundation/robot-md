---
rcan_version: "1.6"
metadata:
  robot_name: old-bot
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

# old-bot

## Identity
Old version.

## What old-bot Can Do
Legacy.

## Safety Gates
Present but rcan_version is too old.
