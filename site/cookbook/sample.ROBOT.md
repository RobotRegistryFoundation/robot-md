---
rcan_version: '3.0'
schema: https://robotmd.dev/schema/v1/robot.schema.json
metadata:
  robot_name: my-robot
  manufacturer: my-robot
  model: minimal
  version: '1.0'
  device_id: my-robot
  rrn: ''
  license: Apache-2.0
network:
  rrf_endpoint: https://robotregistryfoundation.org
  signing_alg: ml-dsa-65
  transports:
  - http
physics:
  type: sensor
  dof: 0
  solver:
    cameras:
    - driver_id: rpi-hevc-dec-video19
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video20
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video21
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video22
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video23
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video24
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video25
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video26
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video27
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video28
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video29
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video30
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video31
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video32
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video33
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video34
      primary_stream: rgb
      mount: world
      extrinsic: null
    - driver_id: pispbe-video35
      primary_stream: rgb
      mount: world
      extrinsic: null
drivers:
- id: host
  protocol: local
  model: cpu
- id: rpi-hevc-dec-video19
  protocol: v4l2
  model: rpi-hevc-dec
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video20
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video21
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video22
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video23
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video24
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video25
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video26
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video27
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video28
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video29
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video30
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video31
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video32
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video33
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video34
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
- id: pispbe-video35
  protocol: v4l2
  model: pispbe
  streams:
    rgb:
      intrinsic: null
capabilities:
- status.report
- vision.describe
safety:
  estop:
    software: true
    response_ms: 0
  failsafe_behavior: stop
  hitl_gates:
  - scope: vision
    require_auth: true
---

# my-robot

## Identity

Sensor-only node with no motion capability.

## What my-robot Can Do

Reports status and observations. No actuation.

## Safety Gates

No physical safety concerns — this node doesn't move.
