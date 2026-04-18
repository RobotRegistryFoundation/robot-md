# Claude Desktop integration (macOS / Windows)

> **Status:** shipped. `robot-md-mcp >= 0.2.1` on npm, `robot-md >= 0.2.6` on PyPI.

Claude Desktop (the Anthropic app for macOS and Windows) speaks the Model Context Protocol. `robot-md-mcp` is an MCP server published to npm that wraps a `ROBOT.md` file as live resources, tools, and prompts. Once registered, Claude Desktop can answer every question about the robot from the manifest, run `/check-safety action="..."` before motion, and invoke `validate` / `render` / `doctor_summary` without shelling out.

## Architecture

```
 ┌─────────────────┐         ┌───────────────────┐          ┌──────────────┐
 │ Claude Desktop  │◄───────►│ npx robot-md-mcp  │◄─ read ──│  ROBOT.md    │
 │   (macOS/Win)   │ stdio   │   (Node process)  │          │  (local file)│
 └─────────────────┘  MCP    └───────────────────┘          └──────────────┘
```

Claude Desktop launches the MCP server as a child process on startup, speaks MCP over stdio, and keeps it alive for the session.

## Install (one command)

```bash
pip install --upgrade robot-md      # ≥ 0.2.6
robot-md install-desktop ROBOT.md   # writes/merges Claude's config
```

That's it. Under the hood, `install-desktop` merge-adds this entry under `mcpServers` in the right OS-specific `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "robot-md": {
      "command": "npx",
      "args": ["-y", "robot-md-mcp", "/absolute/path/to/ROBOT.md"]
    }
  }
}
```

Existing servers (filesystem, github, …) are preserved. Re-running is idempotent. Pass `--force` if you want to replace an already-present `robot-md` entry with a different value.

**Restart Claude Desktop** after install for the change to take effect.

## Config file locations

`install-desktop` writes to the OS-standard path — but if you ever need to edit by hand:

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` *(best-effort — no official Linux build)* |

Use `--config <path>` to target a non-standard location (useful for testing).

## What Claude Desktop sees

Once registered, Claude Desktop's MCP panel shows:

- **6 resources** — `robot-md://<name>/identity | context | frontmatter | capabilities | safety | body`
- **3 tools** — `validate`, `render`, `doctor_summary`
- **4 prompts** (slash commands) — `/brief-me`, `/check-safety`, `/explain-capability`, `/manifest-status`

Each resource and tool advertises an intent-matchable description so Claude routes to them automatically when the operator asks about the robot. The server also publishes an `instructions` field at initialization that tells Claude *when* to use this server — "always read `/safety` before advising any physical motion."

## Verify

1. Open Claude Desktop.
2. Click the connectors/tools indicator — you should see `robot-md` listed as connected.
3. Ask: **"What can this robot do?"** → Claude reads `robot-md://<name>/capabilities`.
4. Try a slash command: type `/brief-me` — Claude produces an at-a-glance summary of the robot.
5. Try safety gating: `/check-safety action="pick up the red cup"` — Claude cross-references the declared `hitl_gates[]` and answers ✓ safe / ⚠ auth-required / ⚠ gate-gap.

If you don't see `robot-md` in the connectors list, restart Claude Desktop once more; it re-reads `claude_desktop_config.json` only on startup.

## Troubleshooting

**"Claude can't find npx"** — macOS Claude Desktop inherits a stripped `PATH`. Either install Node via a system-wide method that places `npx` under `/usr/local/bin` or `/opt/homebrew/bin`, or replace the `"command": "npx"` entry with the absolute path to your npx binary (`which npx`).

**"Validation fails on a perfectly valid ROBOT.md"** — make sure you're on `robot-md-mcp >= 0.1.4`; earlier versions bundled the v1.0 JSON schema and reject v1.1 fields (`physics.solver`, DH params). `npx -y` pulls the latest automatically.

**"Tool calls silently fail"** — check Claude Desktop's MCP log panel; the MCP server logs to stderr, which Claude surfaces there. Common cause: the manifest path in the config moved (e.g., you reorganized directories).

## References

- `robot-md-mcp` npm: <https://www.npmjs.com/package/robot-md-mcp>
- Claude Desktop MCP docs: <https://modelcontextprotocol.io/docs/develop/connect-local-servers#claude-desktop>
- MCP spec: <https://modelcontextprotocol.io/>
