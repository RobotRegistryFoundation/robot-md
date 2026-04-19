# robot-md

> **`ROBOT.md` is to a robot what `CLAUDE.md` is to a codebase.**
> One file — YAML frontmatter + markdown prose — so Claude Code, Claude Desktop, Cursor, Zed, Gemini CLI, or any MCP-aware agent can safely operate your robot.

[![PyPI](https://img.shields.io/pypi/v/robot-md.svg)](https://pypi.org/project/robot-md/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Spec](https://img.shields.io/badge/spec-v1.1-green.svg)](spec/robot-md-v1.md)
[![RCAN](https://img.shields.io/badge/RCAN-3.0-blue.svg)](https://rcan.dev/spec/)

## Where this fits in the stack

This repo is the **declaration layer** — the file format + Python CLI. Everything else is independent; adopt one, or all seven.

| Layer | Piece | What it is |
|---|---|---|
| **Declaration** ← *this* | [ROBOT.md](https://github.com/RobotRegistryFoundation/robot-md) | The file a robot ships at its root. YAML frontmatter + markdown prose. Declares identity, capabilities, safety gates. **Spec + `robot-md` Python CLI** (`init`, `validate`, `render`, `calibrate`, `register`, `autodetect`). |
| **Agent bridge** | [robot-md-mcp](https://github.com/RobotRegistryFoundation/robot-md-mcp) | MCP server that exposes a `ROBOT.md` to Claude Code, Claude Desktop, Cursor, Zed, Gemini CLI — any MCP-aware agent. One `claude mcp add` away. |
| **Wire protocol** | [RCAN](https://rcan.dev/spec/) | How robots, gateways, and planners talk. Signed envelopes, LoA enforcement, PQC crypto. Think HTTP for robots. |
| **Python SDK** | [rcan-py](https://github.com/continuonai/rcan-py) | `pip install rcan` — `RCANMessage`, `RobotURI`, `ConfidenceGate`, `HiTLGate`, `AuditChain`. |
| **TypeScript SDK** | [rcan-ts](https://github.com/continuonai/rcan-ts) | `npm install rcan-ts` — same API surface for Node + browser. |
| **Registry** | [Robot Registry Foundation](https://robotregistryfoundation.org) | Permanent RRN identities. Public resolver at `/r/<rrn>`. Like ICANN for robots. |
| **Reference runtime** | [OpenCastor](https://github.com/craigm26/OpenCastor) | Open-source robot runtime — connects LLM brains to hardware bodies. One implementation of RCAN. |

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

```bash
pip install robot-md
```

Requires Python 3.10+.

## Adopt it for your robot (60 seconds)

Two on-ramps, same destination — Claude Code as the planner and the executor, no OpenCastor, no gateway.

---

### ▶ Option A — On your machine (terminal) *(recommended)*

**For:** operators at a shell prompt on the robot (or a dev laptop with the robot plugged in).

One command does everything — install, scan, draft, register, generate a project-root `CLAUDE.md`, print the MCP add line:

```bash
pip install robot-md && robot-md init my-bob --preset so-arm101 --register \
    --manufacturer acme --contact-email you@acme.com
```

What it does:

1. Installs the `robot-md` CLI.
2. Scans PCI/USB/`/dev/tty*`, matches an SO-ARM101, pre-fills ~85% of the manifest (DH kinematics, servo IDs, safety defaults, capabilities).
3. Mints a public RRN on [rcan.dev](https://rcan.dev) and writes it back into the manifest.
4. **Writes `CLAUDE.md`** next to `ROBOT.md` — an intent→action table that teaches Claude Code which operator phrases should dispatch which `robot-md` verb, what to do before any physical motion, and where to read the safety gates. Existing `CLAUDE.md` content is preserved (append/update-in-place, never overwrite).
5. Prints the MCP add line for Claude Code:

```bash
claude mcp add robot-md -- npx -y robot-md-mcp "$(pwd)/ROBOT.md"
```

> **Two MCP implementations, same protocol.** The default `npx -y
> robot-md-mcp` pulls the TypeScript server from npm (published from
> this repo's TS source). If you'd rather keep everything Python, the
> same CLI is bundled with the pip package — replace the line above
> with `claude mcp add robot-md -- robot-md-mcp "$(pwd)/ROBOT.md"`.
> The TS version exposes `render` + `validate`; the Python version
> (v0.3+) adds `estop`, `execute_capability`, and `execute_task` for
> in-process actuation via a pluggable backend. See
> `docs/mcp-server-options.md` for the full comparison.

6. (Optional) Drop the agent skill into `~/.claude/skills/` so superpowers-aware harnesses auto-invoke robot-md on the operator's first robot-related message:

```bash
robot-md install-skill
```

7. Open Claude Code — it now knows your robot *and* knows when to use the tooling.

```bash
claude
```

**One-command actuatable:** as of v0.5.0, `robot-md init` on a TTY with the arm plugged in also installs the MCP server into Claude Code, installs the `using-robot-md` skill, and prompts Y/n for encoder-sign and zero-pose calibration. On headless runs (no TTY, or `--non-interactive`), these steps auto-skip and init degrades to the old manifest-only behavior. Individual phases can be skipped with `--no-install-mcp`, `--no-install-skill`, `--no-sign`, or `--no-calibrate`.

For custom hardware, swap the preset: `robot-md init my-bob --wizard`. For pure scan-to-draft without a preset, `robot-md autodetect --write ROBOT.md` is the low-level primitive.

**Physical calibration** (for robots with arms): `robot-md calibrate --zero ROBOT.md` — pose the arm at its declared zero, press Enter; the CLI records encoder readings so the manifest's IK solver knows where "zero" is. Preserves YAML comments on rewrite.

### Dev observability

While you work, spin up the local dashboard in a second terminal:

```bash
robot-md dashboard serve --manifest ./ROBOT.md
```

Opens `http://127.0.0.1:8091` — live servo positions, last OAK-D frame, tool-call log, estop button, validator warnings. Data comes from the MCP server's event log at `~/.robot-md/events.jsonl`, which is also the durable record for later replay and memory-sync features. Localhost-only; no auth.

Disable the event log entirely with `ROBOT_MD_DASHBOARD_DISABLED=1`.

---

### ▶ Option B — Inside Claude Code (ask Claude to do it)

**For:** operators who already have Claude Code open and would rather type a sentence than run commands.

In any Claude Code session inside the robot's project directory, paste this prompt:

```
Set up a ROBOT.md for this robot. Use the so-arm101 preset.
Register it publicly at rcan.dev under manufacturer "acme" with my
contact email me@acme.com. Then add the robot-md MCP server to this
session.
```

Claude will use its `Bash` tool to run the same one-liner from Option A, show you the result, and wire up the MCP server for you. See the full walkthrough (including what to paste for custom robots, how to calibrate interactively, and what Claude is allowed to do) in **[`docs/getting-started-claude-code.md`](docs/getting-started-claude-code.md)**.

---

### ▶ Option C — SessionStart hook (pre-MCP path)

If you can't use MCP (older Claude Code, or you want the ROBOT.md context pinned into every session unconditionally):

```bash
mkdir -p ~/.claude/hooks
curl -fsSL https://robotmd.dev/hook > ~/.claude/hooks/robot-md.sh
chmod +x ~/.claude/hooks/robot-md.sh
# Add one entry to ~/.claude/settings.json — see integrations/claude-code/settings.template.json.
```

All three paths end the same way: Claude Code is the planner and the executor. No gateway, no runtime to stand up.

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

## Agent affordances

Beyond the initial setup, the rest of the package is designed so that **Claude Code and other agent harnesses can recognize when to invoke it**, without the operator naming specific tools. Three surfaces work together:

- **`CLAUDE.md` in the project root** — generate with `robot-md claude-md ROBOT.md`. Teaches Claude which operator intents should dispatch which verb (safety → check HITL gates, "broken" → `doctor`, motion → HITL first). Read at session start.
- **MCP server descriptions** — `robot-md-mcp` v0.2+ advertises a server-level `instructions` field plus intent-matchable descriptions on every resource and tool. Any MCP client routes to the right resource by description alone.
- **Skill definition** at [`integrations/claude-code-skill/SKILL.md`](integrations/claude-code-skill/SKILL.md) — for operators running the [superpowers](https://github.com/obra/superpowers) plugin (or any skill-aware harness), a drop-in skill with the intent → action table and a safety protocol Claude follows automatically.

## Claude integration

| Surface | Status | Mechanism |
|---|---|---|
| **Claude Code** (CLI) | ✅ shipped | `claude mcp add robot-md -- npx -y robot-md-mcp ./ROBOT.md` — printed automatically by `robot-md init` |
| **Claude Desktop** (macOS / Windows) | ✅ shipped | One command: `robot-md install-desktop ROBOT.md` merges into `claude_desktop_config.json`. Full MCP — resources + tools + slash commands (`/brief-me`, `/check-safety`, `/explain-capability`, `/manifest-status`). See [`integrations/claude-desktop/`](integrations/claude-desktop/). |
| **Claude Mobile** (iOS / Android) | ✅ shipped (URL-fetch) | Host `ROBOT.md` + `.well-known/robot-md.json` at any public HTTPS URL, paste into the chat. `robot-md publish-discovery` generates the discovery doc. See [`integrations/claude-mobile/`](integrations/claude-mobile/). |
| **OpenAI** (Codex CLI, ChatGPT Desktop) | ✅ shipped | Same MCP server — register `npx -y robot-md-mcp /path/to/ROBOT.md` in the tool's MCP config |
| **Google Gemini CLI** | ✅ shipped | Same MCP server — add to `~/.gemini/settings.json` under `mcpServers` |
| **Cursor / Zed / Cline / Continue.dev / any MCP-aware harness** | ✅ shipped | Same MCP server — register the `npx` command in the tool's MCP settings |

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
