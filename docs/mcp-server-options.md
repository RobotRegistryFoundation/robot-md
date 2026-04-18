# Which MCP server should I use?

`robot-md` ships **two** MCP server implementations that speak the same tool protocol for the `render` and `validate` tools. Choose based on your install story and whether you need in-process actuation.

## Quick decision

- **Just inspecting / validating ROBOT.md?** → either works; pick the one matching your existing toolchain.
- **Need to drive real servos / cameras from tool calls?** → Python (`robot-md-mcp` from `pipx install robot-md`).
- **Multi-language org, no Python toolchain?** → TypeScript (`npx -y robot-md-mcp`).

## Side-by-side

| | TypeScript (`robot-md-mcp` on npm) | Python (`robot-md-mcp` from `pipx install robot-md`) |
|---|---|---|
| Install | `npx -y robot-md-mcp /path/ROBOT.md` (no install, cached by npx) | `pipx install robot-md` then `robot-md-mcp /path/ROBOT.md` |
| `render` tool | ✅ | ✅ |
| `validate` tool | ✅ (errors) | ✅ (errors + warnings for null intrinsic, deprecations) |
| `estop` tool | — | ✅ (process-wide software E-stop) |
| `execute_capability` tool | — | ✅ (deterministic primitive with HITL gates) |
| `execute_task` tool | — | ✅ (NL → planner → capability sequence; anthropic shim) |
| Pluggable `CapabilityBackend` | — | ✅ (entry-point registry; `feetech_depthai` reference) |
| Runtime footprint | Node 18+, ~135 kB | Python 3.10+, ~130 kB core + opt extras |

## Claude Code registration

Pick **one** of these (don't register both at the same key — they'll collide on the MCP `robot-md` name):

```bash
# TypeScript (no install)
claude mcp add robot-md -- npx -y robot-md-mcp "$(pwd)/ROBOT.md"

# Python (after `pipx install robot-md`)
claude mcp add robot-md -- robot-md-mcp "$(pwd)/ROBOT.md"

# Python with the reference feetech+depthai backend for pick-and-place
pipx install "robot-md[feetech-depthai]"
claude mcp add robot-md -- robot-md-mcp "$(pwd)/ROBOT.md"
```

## When the Python-only tools matter

`estop`, `execute_capability`, and `execute_task` need direct, in-process access to the hardware drivers (`/dev/ttyACM0` for Feetech servos, the `depthai` device for OAK-D). A shelled-out subprocess per tool call would add latency and sever the single-instance guarantees (only one motion at a time, estop-flag visibility across calls). The TypeScript MCP is read-only for now — perfect for manifest inspection, not suited for closing the perception-action loop.

If you want actuation but prefer TypeScript, you can run the TS MCP for `render`/`validate` and shell out to a separate execution process — but at that point you're building what the Python MCP does in-process, and most users go with the Python one.

## Both point at the same manifest

There's nothing in `ROBOT.md` that's specific to the server implementation. A manifest written, validated, or rendered by one implementation is valid for the other. You can switch at any time.
