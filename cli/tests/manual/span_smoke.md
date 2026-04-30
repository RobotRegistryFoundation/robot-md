# SP-AN v1 smoke — manual checks on bob

Pre-requisites: SP-HP daemon running. Claude session open in either
voice or text mode. Worktree `pip install -e cli[hardware]` complete.

1. **Voice-mode HIGH-tier auto-bind.** With operator in Claude voice
   mode, replug the SO-ARM101 USB cable on bob. Within 5 s of the plug
   click, Claude announces by voice: "Found an SO-ARM101 on
   /dev/ttyACM0. I bound it as arm_servos using lerobot. Say 'undo' to
   reject." Confirm the announce text appears in chat too.

2. **Voice-mode undo within window.** Same as #1 but the operator says
   "undo" within 30 s. Confirm: a `resolution: reject` record appears
   in `~/.robot-md/hotplug-events.jsonl` for that event_id; the
   manifest still has the driver (manifest unbind is v2).

3. **Voice-mode undo after window.** Same as #1 but the operator says
   "undo" 60 s later. Claude still calls `hotplug_confirm({event_id},
   "reject")`. Claude warns: "the manifest is already bound; want me
   to help unbind by hand?"

4. **Text-mode MEDIUM event.** With operator in text mode (no voice),
   plug a generic CH340 dongle. Claude surfaces the alternatives in
   chat. Operator picks one. Claude passes the choice to
   `hotplug_confirm` with `choice_index`. Manifest gets the driver.

5. **No-Claude-session durability.** Close the Claude session. Plug a
   device. Reopen Claude. The event surfaces in the next interaction
   via the resource update.

6. **Resolved-elsewhere via terminal CLI.** With Claude session open,
   from a separate shell: `robot-md hotplug confirm <event_id> --bind`.
   Claude's next interaction acknowledges: "Got it — I see bind
   happened from the terminal."

## v1 limitation reminder

Items 1, 2, 3 hit the file-poll fallback if the OS doesn't have the
Unix-socket nudge wired (macOS / Windows). Linux gets the sub-second
socket nudge path. Acceptance is "within 5 s" because the file-poll
default interval is 2 s, so worst-case latency is one poll cycle plus
session-read time.
