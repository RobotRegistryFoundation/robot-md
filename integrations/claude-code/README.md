# Claude Code integration

Drop a SessionStart hook into your Claude Code config so that every session launched in a directory containing a `ROBOT.md` gets robot context injected before your first prompt.

## Prerequisites

- Claude Code CLI installed
- `robot-md` CLI installed: `pip install robot-md` (or `pip install -e /path/to/robot-md/cli` for dev)

## Install

```bash
# 1. Copy the hook into your Claude config hooks directory
mkdir -p ~/.claude/hooks
cp /path/to/robot-md/integrations/claude-code/session-start.sh ~/.claude/hooks/robot-md.sh
chmod +x ~/.claude/hooks/robot-md.sh

# 2. Register it in your settings
#    If ~/.claude/settings.json doesn't exist yet, copy our template verbatim:
cp /path/to/robot-md/integrations/claude-code/settings.template.json ~/.claude/settings.json

#    Otherwise, merge the hooks.SessionStart array into your existing settings.json.
```

## Verify

1. Copy `examples/minimal.ROBOT.md` from this repo to a scratch directory as `ROBOT.md`:
   ```bash
   mkdir /tmp/robot-md-test
   cp examples/minimal.ROBOT.md /tmp/robot-md-test/ROBOT.md
   cd /tmp/robot-md-test
   ```

2. Launch Claude Code in that directory:
   ```bash
   claude
   ```

3. Ask: `What robot am I operating?`

   Expected response cites `minimal`, notes it's wheeled with 2 DoF, and mentions the 200 ms software E-stop — all from `ROBOT.md`.

## How it works

When Claude Code launches a session, it runs each `SessionStart` hook. The `robot-md.sh` hook:

1. Checks for `./ROBOT.md` in the session's working directory. If absent, exits silently — no robot here, nothing to inject.
2. Runs `robot-md context ./ROBOT.md`, which emits a markdown block starting with `# Robot context` that includes the robot's identity, declared capabilities, safety envelope, and the prose body of your `ROBOT.md`.
3. Claude Code captures the hook's stdout and includes it in the system prompt for the session.

The result: the planner knows your robot before you ask it anything.

## Troubleshooting

- **Hook doesn't fire**: run `robot-md context ROBOT.md` manually. If it errors, the hook can't help. If it succeeds, check that the path in `~/.claude/settings.json` is correct and the hook is executable (`chmod +x`).
- **"robot-md: command not found"**: `pip install robot-md` in the Python environment Claude Code uses, OR use the absolute path to the CLI in the hook.
- **"failed to parse ROBOT.md"**: run `robot-md validate ROBOT.md` to see what's wrong.

## Next steps

- Write your own `ROBOT.md` — copy `examples/bob.ROBOT.md` and adapt.
- Register your robot with RRF (v0.2 feature — coming soon).
- Use Claude Desktop? See `../claude-desktop/README.md`.
- Use Claude Mobile? See `../claude-mobile/README.md`.
