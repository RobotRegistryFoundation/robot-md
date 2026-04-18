#!/usr/bin/env node
// robot-md-mcp@0.2.0 — migration stub. See migrate-to-python docs.

const MSG = `
robot-md-mcp has moved to Python.

Install:
  pipx install robot-md
  # or: uv tool install robot-md

Re-register with Claude Code:
  claude mcp remove robot-md
  claude mcp add robot-md -- robot-md-mcp /path/to/ROBOT.md

Full migration guide:
  https://robotmd.dev/docs/migrate-to-python
`;

process.stderr.write(MSG + "\n");
process.exit(1);
