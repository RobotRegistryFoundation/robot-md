---
name: using-robot-md
description: Use when the user wants to install, configure, or operate robot-md on a fresh Pi or workstation. Walks the operator through cold install, init, and verification. Don't use for unrelated robotics questions — use only when robot-md is the subject.
---

# Using robot-md

This skill is your guide to getting robot-md installed and running. If you're seeing this on first plugin load, the operator has just installed the plugin and wants to wire up their robot.

## First-time setup recipe

Run these commands in a terminal:

```bash
# 1) Install robot-md from PyPI. On Pi OS Bookworm+ you need --break-system-packages.
python3 -m pip install --user --break-system-packages robot-md

# 2) Initialize a manifest. Replace <name> + email; the preset is so-arm101 by default.
robot-md init <name> --preset so-arm101 --register --contact-email you@example.com

# 3) (Optional, but required for actual motion) Install the enforcement gateway.
robot-md install-gateway

# 4) Health check.
robot-md doctor
```

Each step should take ~30 s. Total cold-install time on a fresh Pi: under 2 minutes.

## When something errors

Paste the error message back to me and I'll figure out the workaround. The most common ones today:

- **PEP 668 `externally-managed-environment`** → `pip install` needs `--break-system-packages` on Pi OS. The robot-md CLI handles this automatically inside `init`, but the first `pip install` step is operator-driven.
- **`claude mcp list` shows "Failed to connect"** → either you haven't `cd`'d into a directory with a `ROBOT.md`, or `ROBOT_MD_PATH` isn't set. Try `export ROBOT_MD_PATH=$HOME/<name>/ROBOT.md`.
- **`/dev/ttyACM0` permission denied** → the gateway claims the device by design. Talk to the gateway at `127.0.0.1:8080`, not the device directly.

## What robot-md gives you in this session

- **MCP resources:** the manifest's frontmatter, capabilities, safety block, and prose body are queryable as resources.
- **MCP tools:** `validate`, `render` (manifest-side); `move`, `home`, `read_state` if the gateway is up.

## What this skill does NOT do

- It does not author or sign INVOKE envelopes. That's a Spec B follow-up; for now use the cookbook recipe or the HIL runner in opencastor-ops.
- It does not move the arm autonomously. Motion always requires the gateway.

## After install

Once `robot-md doctor` returns 0 fails, you're ready for the first prompt: try "what's the state of the robot?" — the MCP should answer from frontmatter resources without any motion.
