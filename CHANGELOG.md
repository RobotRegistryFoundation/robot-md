# Changelog

All notable changes to `robot-md` are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.1.1] - 2026-04-17

### Fixed

- **`robot-md validate` could not find the JSON schema when installed as a wheel.** `validate.py` computed `_SCHEMA_PATH` relative to `__file__` using a four-level `parent` walk that only resolved correctly in the source tree — once `pip install`'d, the path pointed outside `site-packages` and every `validate` call raised `FileNotFoundError`. Fixed by bundling `schema/v1/robot.schema.json` as a package resource under `robot_md/schemas/v1/` and loading it via `importlib.resources.files()`. Canonical schema source remains `schema/v1/robot.schema.json` at the repo root; `scripts/sync-schema.sh` keeps the bundled copy in sync.
- **`robotmd.dev/schema/v1/robot.schema.json` was serving the landing page HTML** instead of the schema (same for `/examples/*`, `/hook`, and `/spec/v1`). Cloudflare Pages SPA-falls-back to `index.html` for missing paths, making the 404 invisible. Added the canonical assets under `site/` so Pages deploys them, with `Content-Type` rules in `_headers` so the schema serves as `application/schema+json`, examples and spec as `text/markdown`, and `/hook` as `text/x-shellscript`. All gain `Access-Control-Allow-Origin: *` for cross-origin validators.

### Security

- Tightened schema bounds on physical-safety fields so manifests claiming absurd values (unbounded velocity, 10-tonne payloads, 10-second E-stop response) are rejected at validation. Full hardened bounds in `SECURITY.md`. Existing examples (Bob, SO-ARM101, minimal, TurtleBot 4) all still validate.
- Added new optional declarative fields: `safety.workspace_bounds_m` (spatial envelope) and `safety.failsafe_behavior` (`stop` / `hold` / `home` / `custom` — planner's mandated behavior on comms loss).
- Added **"Known v0.1 Limitations"** section to `SECURITY.md` documenting gaps in physical safety (manifest is declarative, not enforcing), digital security (no signing yet — planned v0.2), and registry integration (no RRF-side manifest ingestion yet — planned v0.2). Includes the Tier 0 threat model: **"trusted operator + trusted planner"** only; do not expose a Tier 0 robot to untrusted prompts without a gateway layer.

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
