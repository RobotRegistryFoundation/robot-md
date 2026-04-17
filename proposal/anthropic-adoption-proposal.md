# ROBOT.md — An Adoption Proposal for Anthropic

**To:** Anthropic Product + Developer Relations
**From:** craigm26 (Continuon, OpenCastor maintainer)
**Date:** 2026-04-17
**Status:** Draft v0.1

## The ask, in one line

**Treat `ROBOT.md` as a first-class Anthropic convention — the `CLAUDE.md` for physical robots — and ship official support in Claude Code (SessionStart hook), Claude Desktop (MCP server), and Claude Mobile (URL fetch).**

## Why this matters to Anthropic

Claude is the best planner on the market for physical robots. OpenCastor and rcan.dev demonstrate this daily: Bob, our reference 6-DOF arm, runs entirely on Claude Opus 4.7 as the planning brain, with confidence-gated escalation to a local VLA reactive layer for sub-second tasks.

The physical-AI market in 2026 is in flight. Every robotics startup is choosing which LLM to bet on. Configuration-format lock-in is a strong determinant:

- If a robot ships with `ROBOT.md` as Anthropic's canonical format, adopters default to Claude.
- If Anthropic is silent, the market settles on whatever Google or Meta ships first, and robotics becomes a Google/Meta stronghold the way maps and ads are today.

The cost to Anthropic of adoption is small. The cost of non-adoption is structural.

## What `ROBOT.md` is

One file at a robot's project root (or deployment directory), with YAML frontmatter + markdown prose.

- **Frontmatter**: machine-readable declaration of identity, physics, drivers, safety, capabilities, compliance. Validated against a JSON Schema (`https://robotmd.dev/schema/v1/robot.schema.json`).
- **Prose body**: human/LLM-readable capabilities narrative, safety gate rationale, task-routing guidance. Read by Claude at session start.

Parallels `CLAUDE.md` exactly. Operators who already know the `CLAUDE.md` pattern learn `ROBOT.md` in five minutes.

See `../spec/robot-md-v1.md` for the full format spec. See `../examples/bob.ROBOT.md` for a worked example.

## The integration surface

### Claude Code (shipping in robot-md v0.1, today)

A SessionStart hook at `~/.claude/hooks/robot-md.sh` that reads `./ROBOT.md` from the session's cwd and injects a context block. Identical mechanism to how `CLAUDE.md` orients the planner today.

Anthropic adoption level: **endorse** the pattern in Claude Code docs; optionally bundle the hook as a first-class convention (like CLAUDE.md).

### Claude Desktop (shipping in robot-md v0.2)

An MCP server `robot-md-mcp` that exposes ROBOT.md as MCP resources (frontmatter, capabilities, safety) and tools (validate, render, invoke_skill, query_status). The `invoke_skill` tool bridges Claude Desktop to the robot's gateway via RCAN, respecting the `safety.hitl_gates` and `capabilities[]` declared in ROBOT.md.

Anthropic adoption level: **bundle or promote** `robot-md-mcp` as a recommended MCP server. Same pattern as Anthropic's existing recommended MCPs (filesystem, github).

### Claude Mobile / iOS (shipping in robot-md v0.2)

URL-based delivery: operators host ROBOT.md at a stable public URL (or `robotmd.dev/r/<rrn>`). Claude Mobile fetches and reasons over it. No MCP, no tool execution — the copy-paste or invoke-bridge pattern lets operators dispatch commands.

Anthropic adoption level: **document** the URL-fetch pattern in Claude Mobile guides as the canonical way to operate a robot from the phone. (This requires nothing new from Anthropic — Claude Mobile already fetches URLs.)

## Why this isn't an OpenCastor lock-in

- `robot-md` is a **spec + tooling repo**, not a runtime. It has zero OpenCastor dependencies.
- OpenCastor is the reference implementation runtime, but Boston Dynamics Spot, Clearpath TurtleBot, HuggingFace LeRobot, Pollen Reachy — any of them can ship a `ROBOT.md` without importing a single line of OpenCastor code.
- The license is Apache 2.0.
- If Anthropic adopts, the repo can transfer from `craigm26/robot-md` to `Anthropic/robot-md`; craigm26 retains committer status.

## What Anthropic would commit to

- **Documentation**: a page in Claude Code docs titled "ROBOT.md — context for your robot" alongside the existing CLAUDE.md docs.
- **Optional hook bundling**: ship the `robot-md` CLI + SessionStart hook as part of the Claude Code distribution, OR endorse `pip install robot-md` in the docs.
- **MCP recommendation**: list `robot-md-mcp` as an Anthropic-recommended MCP server in Claude Desktop docs when v0.2 ships.
- **Joint announcement**: when the format is stable (v1.0), a co-authored launch blog post or Twitter thread.

**Not** asked:
- No code contributions to Anthropic codebases.
- No exclusivity — ROBOT.md remains an open format; other planners (GPT, Gemini) can consume it freely.
- No IP transfer up-front. Transfer of repo ownership to `Anthropic/robot-md` is offered but optional.

## Evidence from the field

- **OpenCastor** is a production-grade Claude-driven robotics runtime with 7804+ tests, 2 years of CI history, EU AI Act Art. 11/12 compliance, RCAN 3.0 protocol alignment (shipped 2026-04-17), and an active reference robot (Bob, RRN-000000000001).
- **rcan.dev** is the open protocol spec (v3.0 as of April 2026) that ROBOT.md targets. Dozens of robots in community use; full §23-§27 EU AI Act compliance blocks.
- **Robot Registry Foundation** (robotregistryfoundation.org) is the neutral registry that assigns RRNs and hosts public robot declarations. Cloudflare Pages + Workers + D1.

All three are independent of ROBOT.md but compose with it cleanly. The ecosystem is real.

## Timing

- **Today (2026-04-17)**: `robot-md` v0.1 shipped. `robotmd.dev` domain live. Working CLI + hook + examples. Ready for Anthropic review.
- **Next 2 weeks**: v0.2 with RRF registration + Claude Desktop MCP server + TypeScript port.
- **Q3 2026**: v1.0 with frozen spec, conformance suite, multi-language bindings. Ideal target for joint Anthropic announcement.

## Questions to discuss

1. Is there a path to Anthropic-endorsement for community conventions like this, short of full product integration?
2. If we transfer the repo to `Anthropic/robot-md`, what's the governance model? (Committer list, RFC process, breaking-change approval.)
3. Is there interest in bundling the SessionStart hook as a default Claude Code experience, or is recommending `pip install robot-md` in docs sufficient?
4. Would Anthropic product marketing support a joint announcement at v1.0?
5. Who is the right contact inside Anthropic for this? (Product? DevRel? Applied?)

## Contact

- **craigm26** <craigm26@gmail.com>
- GitHub: <https://github.com/craigm26>
- Repo: <https://github.com/craigm26/robot-md>
- Domain: <https://robotmd.dev>
- Supporting ecosystem: <https://opencastor.com> (runtime), <https://rcan.dev> (protocol), <https://robotregistryfoundation.org> (registry)

---

*This proposal is drafted in public (committed to the robot-md repo) so Anthropic reviewers can inspect the full context. Feedback welcome via GitHub issues.*
