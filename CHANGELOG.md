# Changelog

All notable changes to `robot-md` are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Changed

- Repo migrated to the **Robot Registry Foundation** GitHub org (`github.com/RobotRegistryFoundation/robot-md`). Old URL 301-redirects indefinitely. Cloudflare Pages secrets + the `production` and `pypi` GitHub environments were preserved through the transfer; no downstream action required from consumers.
- Dogfood `ROBOT.md` `metadata.manufacturer` updated from `craigm26` to `RobotRegistryFoundation` to match the new steward.

## [0.1.0] - 2026-04-17

### Added

Initial v0.1 release.

- `ROBOT.md` format specification (`spec/robot-md-v1.md`)
- JSON Schema for the frontmatter block (`schema/v1/robot.schema.json`)
- Python CLI `robot-md` with subcommands:
  - `robot-md validate PATH` — schema + RCAN 3.0 conformance check
  - `robot-md render PATH` — strip prose, emit pure YAML
  - `robot-md context PATH` — emit Claude-ready text block
- Four worked examples: `bob.ROBOT.md`, `minimal.ROBOT.md`, `so-arm101.ROBOT.md`, `turtlebot4.ROBOT.md`
- Claude Code SessionStart hook (`integrations/claude-code/session-start.sh`)
- Documented MCP + URL-bridge approaches for Claude Desktop and Mobile
- Draft Anthropic adoption proposal

### Not yet

- `robot-md register` (RRF integration) — planned for v0.2
- Working MCP server for Claude Desktop — planned for v0.2
- URL bridge Cloudflare Worker for Claude Mobile — planned for v0.2
- TypeScript port (`@robotmd/spec`) — planned for v0.2
