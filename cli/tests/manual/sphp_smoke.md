# SP-HP smoke — manual checks on bob

Daemon must be running (`robot-md hotplug-daemon start`) before each step.

1. **Linux: HIGH-tier auto-bind.** Replug SO-ARM101 USB cable on bob.
   Within 1 s the daemon's pyudev path catches it, `classify` returns HIGH
   (single-preset family, single backend installed), `manifest.merge` writes
   a new `drivers[]` entry with `backend: lerobot`. MCP server in an open
   Claude session emits `notifications/tools/list_changed`.

   _Note (2026-04-29): SO-ARM101's CH340 (1a86:7523) currently produces 3
   `family_match` presets in the curated table, so it lands at MEDIUM not
   HIGH. To exercise the HIGH path on bob today, override
   `robot_md.hotplug.presets_index._VID_PID_TO_PRESETS` locally to a single
   `exact_match` entry — or wait for the table to grow per-arm
   discrimination via serial range / chip-revision._

2. **Linux: MEDIUM-tier queue + confirm.** Plug a generic CH340 dongle (no
   serial-unique preset). Daemon classifies MEDIUM. `robot-md hotplug review`
   shows it. `robot-md hotplug confirm <event_id> --bind --choice 0` writes
   the manifest.

3. **macOS: file-poll path.** Same as #1 on macOS. Verify 1–2 s detection
   latency.

4. **Windows: polling fallback.** Same as #1 on Windows. WM_DEVICECHANGE
   message-pump integration is a Windows-host follow-up; polling alone is
   sufficient for v1.

5. **Daemon survives Claude restart.** Plug a generic feetech bus chip mid-
   Claude-session. Kill the Claude session before confirming. Reopen Claude.
   `hotplug_review` still surfaces the pending event.

6. **TTL expiry.** Set `pending_ttl_days = 0.001` in
   `~/.robot-md/hotplug.toml`. Plug a device, leave it pending. Wait 90 s.
   Daemon's expiry sweep appends `resolution: expired` for the original
   pending record.
