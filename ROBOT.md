---
rcan_version: "3.0"
metadata:
  robot_name: robot-md
  manufacturer: craigm26
  model: spec+tooling
  version: "0.1.0"
  license: Apache-2.0

physics:
  type: sensor
  dof: 0

drivers:
  - id: filesystem
    protocol: composite
    model: local-fs

capabilities:
  - status.report

safety:
  estop:
    software: true
    response_ms: 50
---

# robot-md

## Identity

This repo *is* the "robot". It has no motors, no joints, no camera — but it IS a declaration-capable system that ships the format + tooling for every *other* robot's `ROBOT.md`. Dogfooding: if the spec can't describe its own repo as a zero-DoF sensor-class node, the spec isn't complete.

## What robot-md Can Do

- **Status** — run `robot-md --version` or `robot-md validate ROBOT.md` against this file to confirm the tooling is alive.

## Safety Gates

Software E-stop: kill the python process. Response time ~50 ms. No destructive capabilities; nothing here can move in the physical world.
