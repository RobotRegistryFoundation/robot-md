# Claude Desktop integration

> **Status:** v0.1 documents the approach. Working MCP server code lands in v0.2.

Claude Desktop uses the **Model Context Protocol (MCP)** to expose resources and tools to the Claude assistant. `robot-md` integrates via a dedicated MCP server, `robot-md-mcp`, that wraps a `ROBOT.md` file (or URL) as MCP resources and tools.

## Architecture

```
┌─────────────────┐         ┌────────────────┐         ┌──────────────┐
│ Claude Desktop  │◄───────►│ robot-md-mcp   │◄───────►│  ROBOT.md    │
│   (client)      │   MCP   │   (server)     │ read    │ (file or URL)│
└─────────────────┘         └───────┬────────┘         └──────────────┘
                                    │ HTTP
                                    ▼
                           ┌────────────────┐
                           │  Robot gateway │
                           │   (OpenCastor) │
                           └────────────────┘
```

The MCP server exposes:

- **Resources** (read-only, Claude reads at will):
  - `robot-md://<robot_name>/frontmatter` — YAML frontmatter as JSON
  - `robot-md://<robot_name>/capabilities` — the `capabilities[]` list
  - `robot-md://<robot_name>/safety` — the `safety` block
  - `robot-md://<robot_name>/body` — the prose body
- **Tools** (Claude invokes on operator request):
  - `validate` — runs `robot-md validate` and returns the result
  - `render` — returns the frontmatter as YAML
  - `invoke_skill(skill_name, params)` — **bridge**: dispatches an RCAN INVOKE to the robot's gateway URL from `network.ruri`
  - `query_status` — dispatches an RCAN STATUS to the gateway

The `invoke_skill` and `query_status` tools are how Claude Desktop *talks to the robot* through ROBOT.md — the file tells Claude what's allowed, the MCP server executes the dispatch.

## Install (when v0.2 lands)

```bash
# 1. Install the MCP server
pip install robot-md-mcp

# 2. Configure Claude Desktop to use it
#    Edit ~/Library/Application Support/Claude/claude_desktop_config.json
#    (macOS) or the equivalent on Windows/Linux.
```

Example config block (you'll need the full file structure — see Claude Desktop docs):

```json
{
  "mcpServers": {
    "robot-md": {
      "command": "robot-md-mcp",
      "args": ["--robot-md-path", "/path/to/your/ROBOT.md"]
    }
  }
}
```

3. Restart Claude Desktop.

4. Start a new conversation. Claude Desktop will auto-discover the `robot-md` resources. Ask: "What robot do I have configured?" — the response draws from your `ROBOT.md`.

## Design notes for v0.2 implementation

- MCP server uses the official Python MCP SDK (`pip install mcp`).
- `--robot-md-path` can be a local file OR a `https://` URL (for ROBOT.md files hosted at `robotmd.dev/r/<rrn>`).
- Tool `invoke_skill` MUST respect `safety.hitl_gates[]` — if a skill's scope matches a gate with `require_auth: true`, the tool returns an `auth_required` response to Claude, which then prompts the operator for approval before re-dispatching.
- Tool `invoke_skill` MUST NOT allow skill names not present in `capabilities[]` — returns a structured "unknown capability" error.

## Contributing

If you want to land this in v0.2 faster than the maintainers, PRs welcome. The server lives at `integrations/claude-desktop/mcp-server/` (to be created). See the v0.2 milestone on GitHub.

## References

- Model Context Protocol: <https://modelcontextprotocol.io/>
- Claude Desktop MCP docs: <https://docs.claude.com/en/docs/claude-code/mcp>
- RCAN INVOKE / STATUS messages: <https://rcan.dev/spec/section-19/>
