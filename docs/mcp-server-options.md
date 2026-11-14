# Which MCP server should I use?

`robot-md` ships **two** MCP server implementations that speak the same tool protocol for the `render` and `validate` tools. Choose based on your install story and whether you need the motion tools.

## Quick decision

- **Just inspecting / validating ROBOT.md?** → either works; pick the one matching your existing toolchain.
- **Need to move the robot from tool calls?** → Python (`robot-md-mcp` from `pipx install robot-md`), plus [robot-md-gateway](https://github.com/RobotRegistryFoundation/robot-md-gateway) on the robot: the motion tools send to it.
- **Multi-language org, no Python toolchain?** → TypeScript (`npx -y robot-md-mcp`).

## Side-by-side

| | TypeScript (`robot-md-mcp` on npm) | Python (`robot-md-mcp` from `pipx install robot-md`) |
|---|---|---|
| Install | `npx -y robot-md-mcp /path/ROBOT.md` (no install, cached by npx) | `pipx install robot-md` then `robot-md-mcp /path/ROBOT.md` |
| `render` tool | ✅ | ✅ |
| `validate` tool | ✅ (errors) | ✅ (errors + warnings for null intrinsic, deprecations) |
| `estop` / `estop_clear` tools | — | ✅ (`estop` sends robot-md-gateway's declared stop; `estop_clear` always refuses: the person clears a stop with their own credential) |
| `execute_capability` tool | — | ✅ (one declared capability, sent to robot-md-gateway; refuses without one, and refuses every motion while ROBOT.md has a gate that needs a person) |
| `execute_task` tool | — | ✅ (NL → planner → capability sequence, each step sent to robot-md-gateway) |
| Pluggable `CapabilityBackend` | — | ✅ (entry-point registry; `feetech_depthai` reference). The MCP server opens no device by default; `ROBOT_MD_MCP_OPEN_CAMERA=1` opens cameras only, for `vision_find` |
| Runtime footprint | Node 18+, ~135 kB | Python 3.10+, ~130 kB core + opt extras |

## Claude Code registration

Pick **one** of these (don't register both at the same key — they'll collide on the MCP `robot-md` name):

```bash
# TypeScript (no install)
claude mcp add robot-md -- npx -y robot-md-mcp "$(pwd)/ROBOT.md"

# Python (after `pipx install robot-md`)
claude mcp add robot-md -- robot-md-mcp "$(pwd)/ROBOT.md"

# Python with the reference feetech+depthai backend (in-process camera tools)
pipx install "robot-md[feetech-depthai]"
claude mcp add robot-md -- robot-md-mcp "$(pwd)/ROBOT.md"

# Motion needs robot-md-gateway on the robot (the person runs this there)
robot-md install-gateway
```

## When the Python-only tools matter

`estop`, `execute_capability`, and `execute_task` are clients of [robot-md-gateway](https://github.com/RobotRegistryFoundation/robot-md-gateway). Each one sends an RCAN INVOKE envelope to the gateway's `POST /v1/invoke`. The gateway decides (bearer tier, tool allowlist, scope, manifest, its safety state), the actuator behind it bounds and paces the motion, and the gateway records the decision. Nothing in the MCP server opens or writes the servo bus. The server reads the gateway's address from `ROBOT_MD_GATEWAY_URL` (default `http://127.0.0.1:8080`) and an actuate-tier bearer from `ROBOT_MD_GATEWAY_BEARER` or a bearers file it can read; `install-gateway` keeps its own `bearers.yaml` readable by the gateway only, so the person hands the server the token. With no bearer, the motion tools refuse. They need a gateway that includes robot-md-gateway#35, and the server warns when it finds an older one.

`estop_clear` sends nothing and always refuses: clearing a stop makes the robot movable again, so the person does it with their own commission credential, then reconnects the MCP server, which keeps its own latch until it restarts. While ROBOT.md has a gate that needs a person (`require_auth: true`, or not set; every preset that declares gates has one), `execute_capability` and `execute_task` refuse every motion: that person's confirmation has to reach the gateway from outside the conversation, and robot-md has no path for one yet.

Through robot-md 1.10.7, these tools drove the hardware from inside the MCP server process, gated by a `confirm_token` that any non-empty string satisfied. That path is gone: the model that proposes a motion no longer also decides it.

The TypeScript MCP is read-only — perfect for manifest inspection. It has no motion tools.

## Both point at the same manifest

There's nothing in `ROBOT.md` that's specific to the server implementation. A manifest written, validated, or rendered by one implementation is valid for the other. You can switch at any time.
