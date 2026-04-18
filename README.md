# robot-md

> **`ROBOT.md` is to a robot what `CLAUDE.md` is to a codebase.**
> One file — YAML frontmatter + markdown prose — so Claude (Code, Desktop, Mobile) can safely operate your robot.

[![PyPI](https://img.shields.io/pypi/v/robot-md.svg)](https://pypi.org/project/robot-md/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Spec](https://img.shields.io/badge/spec-v1-green.svg)](spec/robot-md-v1.md)
[![RCAN](https://img.shields.io/badge/RCAN-3.0-blue.svg)](https://rcan.dev/spec/)

## The 60-second pitch

Every robot today is described in 5+ files: a YAML config, a P66 manifest, a CLAUDE.md, a firmware manifest, a README. They drift. When you add a joint, three files need updates.

`ROBOT.md` is the single source of truth. Drop one file at your robot's project root:

```markdown
---
rcan_version: "3.0"
metadata:
  robot_name: bob
physics:
  type: arm+camera
  dof: 6
drivers:
  - { id: arm, protocol: feetech, port: /dev/ttyUSB0 }
capabilities:
  - arm.pick
  - arm.place
  - vision.describe
safety:
  payload_kg: 0.5
  estop: { software: true, response_ms: 100 }
  hitl_gates:
    - { scope: destructive, require_auth: true }
---

# bob

## Identity
Bob is a 6-DOF SO-ARM101 arm with an OAK-D camera.

## What bob Can Do
Pick, place, describe what the camera sees. Max payload 0.5 kg.

## Safety Gates
Software E-stop at 100 ms. Destructive actions require human approval.
```

Now Claude — in Code, Desktop, or Mobile — knows your robot.

## Why it works

- **Machine-readable**: frontmatter validates against a [JSON Schema](schema/v1/robot.schema.json). Runtime tools consume it directly.
- **LLM-readable**: the prose body tells Claude *why* — which actions are dangerous, which need HITL, how the robot's capabilities map to real-world tasks.
- **One file**: no more drift between config, manifest, and README.

## Install

PyPI publish is imminent; until then, install from the repo:

```bash
pip install git+https://github.com/RobotRegistryFoundation/robot-md.git#subdirectory=cli
```

Once `robot-md` lands on PyPI:

```bash
pip install robot-md
```

Requires Python 3.10+.

## Adopt it for your robot (60 seconds)

The Tier 0 flow — Claude Code alone as the runtime, no OpenCastor.

### Option A — Claude Code via MCP *(recommended)*

Three commands, zero config files:

```bash
# 1. Zero-to-ROBOT.md, one command. Auto-matches a preset (SO-ARM101,
#    TurtleBot 4, PiCar-X, ...) and pre-fills ~85% of the manifest for
#    known robots: DH kinematics, servo IDs, safety defaults, capabilities.
cd ~/my-robot
robot-md init my-bob --preset so-arm101
# → ✓ wrote ROBOT.md (arm, 6 DoF, 5 capabilities, preset: so-arm101)

# 2. Tell Claude Code about it (one line — no settings.json editing)
claude mcp add robot-md -- npx -y robot-md-mcp "$(pwd)/ROBOT.md"

# 3. Open Claude Code. It now knows your robot.
claude
```

For custom hardware, `robot-md init --wizard` walks you through 7 steps.
For pure scan-to-draft without a preset, `robot-md autodetect --write
ROBOT.md` still works as the low-level primitive.

Claude Code gets the robot's frontmatter, capabilities, safety gates, and prose body as MCP resources. **No harness config, no provider setup, no YAML wrangling** — built for operators who just want Claude Code to understand the robot. See [`robot-md-mcp`](https://github.com/RobotRegistryFoundation/robot-md-mcp) for the MCP server.

**Physical calibration** (for robots with arms): `robot-md calibrate --zero ROBOT.md` pose the arm at its declared zero config, press Enter — the CLI records the encoder readings so the manifest's baseline IK solver knows where "zero" is. Preserves YAML comments on rewrite.

### Option B — SessionStart hook (pre-MCP path)

If you can't use MCP (e.g. older Claude Code, or you want the ROBOT.md context pinned into every session unconditionally):

```bash
mkdir -p ~/.claude/hooks
curl -fsSL https://robotmd.dev/hook > ~/.claude/hooks/robot-md.sh
chmod +x ~/.claude/hooks/robot-md.sh
# Add one entry to ~/.claude/settings.json — see integrations/claude-code/settings.template.json.
```

Both paths end the same way: Claude Code is the planner and the executor. No gateway, no runtime to stand up.

`robot-md autodetect` scans PCI + USB + `/dev/tty*` and emits a draft that validates against the v1 schema but deliberately marks identity fields (`robot_name`, `physics.type`, `dof`) as TODO — the operator is the authority on what the robot *is*.

**Want a public identity?** `robot-md register ROBOT.md` (shipping in v0.2) posts to the Robot Registry Foundation, writes the assigned `RRN-XXXXXXXXXXXX` into your manifest, and anchors your robot's signing key.

**Want fleet-grade orchestration, P66 hardware interlocks, reactive VLA control, or EU AI Act audit?** Add [OpenCastor](https://github.com/craigm26/OpenCastor) when the time comes. Until then, ROBOT.md + Claude Code is all you need.

## Inspect a ROBOT.md (CLI)

```bash
robot-md autodetect                      # print a draft ROBOT.md to stdout
robot-md autodetect --write ROBOT.md     # write it (refuses to overwrite)

robot-md validate examples/bob.ROBOT.md
# → ✓ bob (arm+camera, 6 DoF, 5 capabilities)

robot-md render examples/bob.ROBOT.md | head -5
# strips prose, emits pure YAML for runtime tooling

robot-md context examples/bob.ROBOT.md | head -10
# emits the Claude-ready '# Robot context' block
```

## Claude integration

| Surface | Status | Mechanism |
|---|---|---|
| **Claude Code** | ✅ v0.1 | **`claude mcp add robot-md -- npx -y robot-md-mcp ./ROBOT.md`** via [`robot-md-mcp`](https://github.com/RobotRegistryFoundation/robot-md-mcp) *(recommended)* · alt: SessionStart hook → `robot-md context` |
| **Claude Desktop** | ✅ v0.1 (read-only) | [`robot-md-mcp`](https://github.com/RobotRegistryFoundation/robot-md-mcp) — resources + validate/render; dispatch tools arrive with v0.2 signing |
| **Claude Mobile (iOS)** | 🚧 v0.2 | URL fetch: `https://robotmd.dev/r/<rrn>` |
| **OpenAI** (Codex CLI, ChatGPT Desktop) | ✅ v0.1 | Same MCP server — register `npx -y robot-md-mcp /path/to/ROBOT.md` in the tool's MCP config |
| **Google Gemini CLI** | ✅ v0.1 | Same MCP server — add to `~/.gemini/settings.json` under `mcpServers` |
| **Cursor / Zed / Cline / Continue.dev / any MCP-aware harness** | ✅ v0.1 | Same MCP server — register the `npx` command in the tool's MCP settings |

**ROBOT.md is planner-agnostic by design.** MCP is an [open standard](https://modelcontextprotocol.io). The file you write is the file every provider reads. No per-vendor rewrites, no parallel manifests.

See [`integrations/claude-code/`](integrations/claude-code/) for hook-path install instructions. The MCP path needs no files — just the `claude mcp add` one-liner (or your harness's equivalent) above.

## The broader ecosystem

```
  ROBOT.md (this repo)     →  what the robot IS
  OpenCastor               →  what the robot RUNS   (github.com/craigm26/OpenCastor)
  RCAN                     →  what the robot SPEAKS (rcan.dev)
  Robot Registry Foundation → where the robot LIVES (robotregistryfoundation.org)
```

Each layer is independent. Use ROBOT.md without OpenCastor (just for Claude context). Use OpenCastor without ROBOT.md (the old YAML-only path). Compose them for the full flow.

## Spec + docs

- **[Format spec v1](spec/robot-md-v1.md)** — the authoritative definition of what goes in a ROBOT.md.
- **[Rationale](spec/rationale.md)** — design decisions + why.
- **[JSON Schema](schema/v1/robot.schema.json)** — draft 2020-12.
- **[Examples](examples/)** — 4 worked ROBOT.md files (Bob, so-arm101, TurtleBot 4, minimal).
- **[v0.2 design (draft)](spec/v0.2-design.md)** — signing, registry ingestion, tamper-evidence. Design only; no code yet. Feedback welcome.

## Scope

### In scope

- The ROBOT.md file format (spec + schema + examples)
- A reference Python CLI (validate / render / context)
- Claude Code integration hook

### Out of scope

- Robot runtime code — that's [OpenCastor](https://github.com/craigm26/OpenCastor).
- Registry implementation — that's [RRF](https://robotregistryfoundation.org/).
- Wire protocol — that's [RCAN](https://rcan.dev/).
- Skill implementation framework — OpenCastor's `SkillRegistry`.

This repo is spec + tooling only. A hard line.

## Contributing

- Open an issue to propose a spec change; breaking changes require a design doc.
- Small, focused PRs welcome.
- See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full guide (tests, lint, commit style).

## License

Apache 2.0 — see [`LICENSE`](LICENSE).

## Links

- Homepage: <https://robotmd.dev>
- PyPI: <https://pypi.org/project/robot-md/>
- OpenCastor: <https://github.com/craigm26/OpenCastor>
- RCAN spec: <https://rcan.dev>
- Robot Registry Foundation: <https://robotregistryfoundation.org>
