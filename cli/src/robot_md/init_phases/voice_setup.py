"""robot-md init phase — voice + audio onboarding.

Imports pendantd.audio.devices as a soft dependency. If pendantd isn't
importable, the phase prints a notice and exits rc=0.
"""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import yaml

_HEADER = "═══ Voice setup ═══════════════════════════════════════════"


def _try_import_pendantd():
    try:
        from pendantd.audio import devices as devs_mod  # type: ignore

        return devs_mod
    except Exception:
        return None


def _prompt_choice(prompt: str, options: list, default_idx: int = 0) -> int:
    sys.stdout.write(prompt + "\n")
    for i, o in enumerate(options, 1):
        marker = "  ←  auto-pick" if i - 1 == default_idx else ""
        sys.stdout.write(f"  [{i}] {o.name}{marker}\n")
    sys.stdout.write("  [ ] Press Enter to accept auto-pick, or type a number: ")
    sys.stdout.flush()
    line = sys.stdin.readline().strip()
    if not line:
        return default_idx
    try:
        n = int(line)
        if 1 <= n <= len(options):
            return n - 1
    except ValueError:
        pass
    return default_idx


def _confirm(prompt: str) -> bool:
    sys.stdout.write(prompt + " [Y/n] ")
    sys.stdout.flush()
    line = sys.stdin.readline().strip().lower()
    return line in ("", "y", "yes")


def _speaker_test(output_device_name: str) -> bool:
    """Play a 1s 880Hz tone via the chosen output. Returns True if user confirmed."""
    try:
        import asyncio
        import math
        import struct

        from pendantd.audio.devices import list_devices, match_substring  # type: ignore
        from pendantd.audio.streams import OutputStream  # type: ignore

        devs = list_devices()
        device = match_substring(devs.outputs, output_device_name)
        if device is None:
            sys.stdout.write(
                f"  (couldn't find output device matching {output_device_name!r}; skipping tone)\n"
            )
            return _confirm("Hear it?")

        # Generate 1s of 880Hz tone, mono int16 at the device's preferred rate
        sr = device.sample_rate
        n = int(1.0 * sr)
        amp = 8000  # ~25% of int16 max — comfortable
        tone = struct.pack(
            f"<{n}h",
            *[int(amp * math.sin(2 * math.pi * 880 * t / sr)) for t in range(n)],
        )

        async def _play() -> None:
            stream = OutputStream(device_index=device.index, samplerate=sr)
            await stream.start()
            try:
                await stream.write(tone)
                await asyncio.sleep(1.1)  # let the tone finish
            finally:
                await stream.stop()

        sys.stdout.write(f"Speaker test… playing 880 Hz via {device.name}\n")
        asyncio.run(_play())
    except Exception as e:
        sys.stdout.write(f"  (speaker test failed: {e}; falling back to manual confirmation)\n")
    return _confirm("Hear it?")


def _mic_loopback_test(input_name: str, output_name: str) -> bool:
    """Record 2s, play it back. Returns True if user confirmed."""
    try:
        import asyncio

        from pendantd.audio.devices import list_devices, match_substring  # type: ignore
        from pendantd.audio.loopback import record_and_play  # type: ignore
        from pendantd.audio.streams import InputStream, OutputStream  # type: ignore

        devs = list_devices()
        in_dev = match_substring(devs.inputs, input_name)
        out_dev = match_substring(devs.outputs, output_name)
        if in_dev is None or out_dev is None:
            sys.stdout.write("  (couldn't find devices for loopback; skipping)\n")
            return _confirm("Sound right?")

        async def _loopback():
            inp = InputStream(device_index=in_dev.index, samplerate=in_dev.sample_rate)
            out = OutputStream(device_index=out_dev.index, samplerate=in_dev.sample_rate)
            return await record_and_play(inp, out, seconds=2.0)

        sys.stdout.write(
            f"Mic loopback test… recording 2s via {in_dev.name}, playing back via {out_dev.name}\n"
        )
        result = asyncio.run(_loopback())
        sys.stdout.write(
            f"  recorded {result.recorded_bytes} bytes (peak {result.peak_dbfs:.1f} dBFS)\n"
        )
    except Exception as e:
        sys.stdout.write(f"  (loopback failed: {e}; falling back to manual confirmation)\n")
    return _confirm("Sound right?")


def run_voice_setup(
    robot_name: str,
    cfg_path: Path,
    non_interactive: bool = False,
    _skip_wake_check: bool = False,
) -> int:
    """Returns rc (0 on success, even when no audio devices were found)."""
    devs_mod = _try_import_pendantd()
    if devs_mod is None:
        sys.stdout.write(
            "pendantd not detected; skipping voice setup.\n"
            "  (pendantd is the optional voice/wake-word daemon. Install with\n"
            "  `pip install pendantd` if you want push-to-talk; safe to skip otherwise.)\n"
        )
        return 0

    sys.stdout.write(_HEADER + "\n")
    sys.stdout.write("Detecting audio devices…\n")
    devs = devs_mod.list_devices()

    cfg = {
        "wake_word": "claude",
        "robot_name": robot_name or "",
        "wake_aliases": [],
        "input_device": "",
        "output_device": "",
        "sample_rate": 16000,
        "tts_voice": "en_US-amy-medium",
    }

    if not devs.inputs and not devs.outputs:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(
            "# TODO(voice): no audio devices detected at init time\n" + yaml.safe_dump(cfg)
        )
        sys.stdout.write(
            "No audio devices detected. Wrote a TODO marker; re-run when devices attach.\n"
        )
        return 0

    in_default = devs_mod.pick_default(devs.inputs, kind="input") if devs.inputs else None
    out_default = (
        devs_mod.pick_default(devs.outputs, kind="output", all_devices=devs)
        if devs.outputs
        else None
    )

    if non_interactive:
        cfg["input_device"] = in_default.name if in_default else ""
        cfg["output_device"] = out_default.name if out_default else ""
    else:
        if devs.inputs:
            default_idx = devs.inputs.index(in_default) if in_default else 0
            idx = _prompt_choice("Inputs:", devs.inputs, default_idx=default_idx)
            cfg["input_device"] = devs.inputs[idx].name
        if devs.outputs:
            default_idx = devs.outputs.index(out_default) if out_default else 0
            idx = _prompt_choice("Outputs:", devs.outputs, default_idx=default_idx)
            cfg["output_device"] = devs.outputs[idx].name

        # Speaker test
        if cfg["output_device"] and not _speaker_test(cfg["output_device"]):
            sys.stdout.write("Output may need attention. Continuing.\n")
        # Mic loopback test
        if (
            cfg["input_device"]
            and cfg["output_device"]
            and not _mic_loopback_test(cfg["input_device"], cfg["output_device"])
        ):
            sys.stdout.write("Input may need attention. Continuing.\n")
        # Wake-word check
        if not _skip_wake_check and cfg["robot_name"]:
            sys.stdout.write(f'Wake-word check… say "{cfg["robot_name"]}" or "claude" within 10s\n')
            sys.stdout.write("(deferred to runtime — re-run with `pendantd voice test-wake`)\n")

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    _now = _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds")
    provenance = f"# Provenance: autodetected {_now}; first input that matched USB class.\n"
    cfg_path.write_text(yaml.safe_dump(cfg) + provenance)
    sys.stdout.write(f"Wrote {cfg_path}.\n")
    return 0


# ---------------------------------------------------------------------------
# Phase adapter — converts run_voice_setup's int rc to PhaseResult so this
# phase can be wired into default_flow alongside the other init phases.
# ---------------------------------------------------------------------------

from pathlib import Path as _Path  # noqa: E402 (below module-level code)

from robot_md.init_phases import PhaseResult as _PhaseResult  # noqa: E402


def phase_voice_setup(
    manifest_path: _Path,
    *,
    non_interactive: bool = False,
) -> _PhaseResult:
    """Adapter: run voice/audio onboarding and return a PhaseResult.

    Derives the robot_name from the manifest's frontmatter.
    The voice config is written to ``<manifest_dir>/.robot-md/voice.yaml``.
    Always returns status="ok" when pendantd is missing (soft dependency).
    """
    robot_name = ""
    try:
        from robot_md.parser import parse_file

        parsed = parse_file(manifest_path)
        robot_name = (parsed.frontmatter.get("metadata") or {}).get("robot_name", "") or ""
    except Exception:
        pass  # robot_name stays ""; run_voice_setup handles empty gracefully

    cfg_path = manifest_path.parent / ".robot-md" / "voice.yaml"
    rc = run_voice_setup(robot_name, cfg_path=cfg_path, non_interactive=non_interactive)

    if rc == 0:
        return _PhaseResult(
            phase="voice_setup",
            status="ok",
            message=f"voice config written to {cfg_path}",
            detail={"cfg_path": str(cfg_path), "robot_name": robot_name},
        )
    return _PhaseResult(
        phase="voice_setup",
        status="failed",
        message=f"run_voice_setup exited with rc={rc}",
        detail={"rc": rc, "cfg_path": str(cfg_path)},
    )
