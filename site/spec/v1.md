# ROBOT.md Format Specification — v1

**Status:** Draft (v0.1)
**Date:** 2026-04-17
**Authors:** craigm26 et al.
**License:** Apache-2.0 (same as repo)

## 1. Overview

`ROBOT.md` is a single file that declares what a robot **is** and what it **can do**, in a form that both machines (JSON Schema + RCAN validators) and LLM planners (Claude Opus 4.7, Sonnet, etc.) can consume directly.

The file is markdown with a leading YAML frontmatter block:

- The **frontmatter** is the machine-readable declaration: identity, physics, drivers, safety, capabilities, compliance. Validated against `schema/v1/robot.schema.json`.
- The **body** is human/LLM prose: identity narrative, capabilities explained, safety gates described, task-routing guidance. Read by the planner at session start.

This parallels `CLAUDE.md`'s role for codebases: a single file, read at session start, that orients the planner.

## 2. File structure

```
---
<YAML frontmatter>
---

<Markdown body>
```

The frontmatter delimiters MUST be exactly three hyphens (`---`) on their own lines. The frontmatter MUST be valid YAML 1.1 (compatible with PyYAML `safe_load`). The body MAY be empty but MUST be present (at minimum a single `# <robot_name>` H1).

## 3. Frontmatter — required fields

### 3.1 `rcan_version` (string, required)

The RCAN protocol version this ROBOT.md conforms to. MUST be one of:

- `"3.0"` — current (recommended)
- `"2.2"`, `"2.1"` — accepted via OpenCastor compatibility mode but operators should migrate
- Future `3.x` versions (forward-compatible per `castor.compliance.is_accepted_version`)

Rejected: `"1.x"` (EU AI Act compliance gap; ROBOT.md requires v2.1+).

### 3.2 `metadata` (map, required)

| Field | Type | Required | Description |
|---|---|---|---|
| `robot_name` | string | ✅ | Short display name (e.g., `bob`) |
| `rrn` | string | recommended | RRF-assigned RRN, or empty string until registered |
| `rrn_uri` | string | recommended | Canonical URI form of the RRN |
| `ruri` | string | recommended | Gateway URL (e.g., `rcan://robot.local:8001/bob`) |
| `manufacturer` | string | optional | Vendor or operator |
| `model` | string | optional | Model identifier |
| `version` | string | optional | Firmware/deployment version |
| `license` | string | optional | SPDX license identifier |

### 3.3 `physics` (map, required)

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | ✅ | `arm` \| `wheeled` \| `tracked` \| `legged` \| `arm+camera` \| `humanoid` \| `other` |
| `dof` | int | ✅ | Degrees of freedom (0 for purely sensory robots) |
| `kinematics` | array | optional | Per-joint entries (required if `type` is arm-based and `dof > 0`) |

Each kinematics entry:

```yaml
- id: shoulder_pan
  axis: x | y | z
  limits_deg: [min, max]   # or limits_mm for prismatic joints
  length_mm: 60            # link length downstream of this joint
```

### 3.4 `drivers` (array, required)

A list of hardware drivers the robot uses. At least one entry is required. Each driver declares `id` and `protocol`; additional fields are protocol-specific.

```yaml
drivers:
  - id: arm_servos
    protocol: feetech       # feetech | dynamixel | pca9685 | gpio | ros2 | ...
    port: /dev/ttyUSB0
    baud_rate: 1000000
    model: STS3215
    count: 6
  - id: camera
    protocol: depthai
    model: OAK-D
```

Recognized protocols match `castor.drivers.<name>` in OpenCastor (full list: `spec/rationale.md`).

### 3.5 `safety` (map, required)

| Field | Type | Required | Description |
|---|---|---|---|
| `p66_enabled` | bool | recommended | P66 safety manifest active |
| `loa_enforcement` | bool | recommended | RCAN Level-of-Assurance enforcement |
| `max_joint_velocity_dps` | number | if applicable | Max degrees/sec across all joints |
| `max_linear_velocity_ms` | number | if applicable | Max m/s (wheeled/tracked) |
| `payload_kg` | number | if applicable | Max payload |
| `estop` | map | ✅ | E-stop configuration — see below |
| `hitl_gates` | array | recommended | Human-in-the-loop gate scopes |

The `estop` map:

```yaml
estop:
  hardware: false           # dedicated physical button?
  software: true            # software interrupt supported
  response_ms: 100          # time from trigger to motion-halt
```

At minimum, `software: true` with `response_ms` is required.

## 4. Frontmatter — conditionally required

### 4.1 `capabilities` (array of strings, required if `physics.dof > 0`)

Named skills the robot exposes. Each name SHOULD map to a skill registered in the deploying runtime's `SkillRegistry`. Standard namespaces:

- `nav.*` — navigation (move, stop, go_to)
- `arm.*` — manipulation (pick, place, reach, grip)
- `vision.*` — perception (describe, detect, track)
- `status.*` — introspection (report, health)
- `system.*` — lifecycle (shutdown, reboot, calibrate)

Vendor-specific skills MAY use their own namespace (e.g., `bosdyn.crouch`).

### 4.2 `network` (map, required for network-addressable robots)

| Field | Type | Description |
|---|---|---|
| `rrf_endpoint` | URL | `https://robotregistryfoundation.org` or self-hosted RRF |
| `port` | int | Gateway port |
| `signing_alg` | string | `pqc-hybrid-v1` (required at RCAN 3.0 L2+); `ml-dsa-65`; or `ed25519` (L1 only, sunset in 3.x) |
| `transports` | array | `[http, mqtt, ws]` etc. |

### 4.3 `brain` (map, required if the robot uses an LLM planner)

| Field | Type | Description |
|---|---|---|
| `planning` | map | LLM provider + model + confidence gate |
| `reactive` | map | Optional low-latency layer (e.g., VLA model) |
| `task_routing` | map | RCAN task-category routing overrides |

Example:

```yaml
brain:
  planning:
    provider: anthropic
    model: claude-opus-4-7
    confidence_gate: 0.60
  reactive:
    provider: local
    model: openvla-7b
  task_routing:
    sensor_poll: fast_only
    safety: planner_always
    navigation: periodic
    reasoning: planner
```

### 4.4 `compliance` (map, required for EU-deployed robots)

| Field | Type | Description |
|---|---|---|
| `fria_ref` | URL or null | Signed Fundamental Rights Impact Assessment document URI (RCAN §27). `null` = placeholder pending `castor fria generate`. |
| `iso_42001` | map | `{ self_assessed: bool, level: 1-5 }` |
| `eu_ai_act` | map | `{ audit_retention_days: int }` (≥ 365 for Annex III systems) |

## 5. Body — required sections

The markdown body MUST contain:

1. `# <metadata.robot_name>` — H1 matching `metadata.robot_name` (case-insensitive)
2. `## Identity` — 1-2 paragraphs describing the robot
3. `## What <robot_name> Can Do` — prose capability narrative
4. `## Safety Gates` — which actions gated, how E-stop works

Optional sections:

- `## Task Routing` — expands on `brain.task_routing`
- `## Extension Points` — how to add skills/drivers
- `## References` — links to spec, runtime, RRF entry

## 6. Body — planner usage

A Claude session with this ROBOT.md in context at startup is expected to:

1. Cite the robot by name in its first response
2. Respect `safety.hitl_gates` without prompting
3. Route tasks according to `brain.task_routing`
4. Refuse capabilities NOT listed in `capabilities[]`
5. Honor `compliance` flags (e.g., extra caution for `eu_ai_act.audit_retention_days > 0`)

## 7. Extensions

Vendor-specific extensions MUST use the `extensions:` block with namespaced keys:

```yaml
extensions:
  x-opencastor:
    harness_ref: /etc/opencastor/harness.yaml
  x-boston-dynamics:
    spot_config_version: "3.2"
```

Unknown `extensions.x-*` keys MUST NOT cause validation failure.

## 8. Validation

A ROBOT.md is **valid** if and only if:

1. Frontmatter parses as YAML without error
2. Frontmatter validates against `schema/v1/robot.schema.json`
3. `rcan_version` passes `castor.compliance.is_accepted_version` (or equivalent — see rationale)
4. Required body sections are present
5. `capabilities` values match `nav.*`, `arm.*`, `vision.*`, `status.*`, `system.*`, or vendor `<prefix>.*` patterns

The `robot-md validate` CLI returns exit codes:

- `0` — valid
- `1` — file not found or parse error
- `2` — schema violation
- `3` — RCAN conformance violation
- `4` — missing required body section

## 9. Versioning

The spec version is `v1`. Future versions:

- `v1.x` — backward-compatible additions (new optional fields, new optional sections)
- `v2` — breaking changes (field renames, required→optional changes that affect validation)

Breaking changes live at a new schema URL (`schema/v2/robot.schema.json`) and the spec file is renamed accordingly. Both served indefinitely.

## 10. References

- RCAN protocol: <https://rcan.dev/spec/>
- Robot Registry Foundation: <https://robotregistryfoundation.org/>
- OpenCastor runtime: <https://github.com/craigm26/OpenCastor>
- JSON Schema spec: <https://json-schema.org/draft/2020-12/>
