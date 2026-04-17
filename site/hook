#!/usr/bin/env bash
# robot-md Claude Code SessionStart hook.
#
# Reads ./ROBOT.md from the session's cwd (if present) and feeds a
# Claude-ready context block to stdout. Claude Code injects stdout
# from SessionStart hooks into the session's system context.
#
# Install: symlink or copy into ~/.claude/hooks/robot-md.sh, then
# reference in .claude/settings.json (see settings.template.json).

set -euo pipefail

# Look for ROBOT.md in cwd. If absent, silently exit (no robot here).
if [[ ! -f "./ROBOT.md" ]]; then
  exit 0
fi

# Require robot-md CLI to be on PATH.
if ! command -v robot-md >/dev/null 2>&1; then
  >&2 echo "robot-md: CLI not on PATH. Install: pip install robot-md"
  exit 0  # non-fatal — we don't want to break the session
fi

# Emit the context block to stdout.
robot-md context ./ROBOT.md
