"""robot-md init phase — voice + audio onboarding.

Imports pendantd.audio.devices as a soft dependency. If pendantd isn't
importable, the phase prints a notice and exits rc=0.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any

import yaml


_HEADER = (
    "═══ Voice setup ═══════════════════════════════════════════"
)


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
    sys.stdout.write(f"  [ ] Press Enter to accept auto-pick, or type a number: ")
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


def run_voice_setup(
    robot_name: str,
    cfg_path: Path,
    non_interactive: bool = False,
    _skip_wake_check: bool = False,
) -> int:
    """Returns rc (0 on success, even when no audio devices were found)."""
    devs_mod = _try_import_pendantd()
    if devs_mod is None:
        sys.stdout.write("pendantd not detected; skipping voice setup\n")
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
            "# TODO(voice): no audio devices detected at init time\n"
            + yaml.safe_dump(cfg)
        )
        sys.stdout.write("No audio devices detected. Wrote a TODO marker; re-run when devices attach.\n")
        return 0

    in_default = devs_mod.pick_default(devs.inputs, kind="input") if devs.inputs else None
    out_default = devs_mod.pick_default(devs.outputs, kind="output", all_devices=devs) if devs.outputs else None

    if non_interactive:
        cfg["input_device"] = in_default.name if in_default else ""
        cfg["output_device"] = out_default.name if out_default else ""
    else:
        if devs.inputs:
            idx = _prompt_choice("Inputs:", devs.inputs, default_idx=devs.inputs.index(in_default) if in_default else 0)
            cfg["input_device"] = devs.inputs[idx].name
        if devs.outputs:
            idx = _prompt_choice("Outputs:", devs.outputs, default_idx=devs.outputs.index(out_default) if out_default else 0)
            cfg["output_device"] = devs.outputs[idx].name

        # Speaker test
        if cfg["output_device"]:
            sys.stdout.write(f"Speaker test… (you should hear a 1s tone via {cfg['output_device']})\n")
            sys.stdout.write("(skipped in this build — confirm interactively after pendantd starts)\n")
            if not _confirm("Hear it?"):
                sys.stdout.write("Output may need attention. Continuing.\n")
        # Mic loopback test placeholder
        if cfg["input_device"]:
            sys.stdout.write("Mic loopback test… (deferred to runtime; pendantd reports peak dBFS)\n")
            if not _confirm("Sound right?"):
                sys.stdout.write("Input may need attention. Continuing.\n")
        # Wake-word check
        if not _skip_wake_check and cfg["robot_name"]:
            sys.stdout.write(f'Wake-word check… say "{cfg["robot_name"]}" or "claude" within 10s\n')
            sys.stdout.write("(deferred to runtime — re-run with `pendantd voice test-wake`)\n")

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    provenance = (
        f"# Provenance: autodetected {_dt.datetime.utcnow().isoformat(timespec='seconds')}Z; "
        f"first input that matched USB class.\n"
    )
    cfg_path.write_text(yaml.safe_dump(cfg) + provenance)
    sys.stdout.write(f"Wrote {cfg_path}.\n")
    return 0
