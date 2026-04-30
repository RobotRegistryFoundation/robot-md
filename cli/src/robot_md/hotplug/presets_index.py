"""VID:PID → preset lookup, built from existing presets at import time.

We trade preset YAML round-tripping for an explicit hint table here: presets
themselves don't currently declare VID:PID (that's a future SP3.x extension).
Until they do, this module ships a hand-curated mapping derived from each
preset's documented hardware.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresetMatch:
    preset_name: str
    transport: str
    confidence: str  # "exact_match" | "family_match"


# Hand-curated initial table; expand via PR as new presets land.
_VID_PID_TO_PRESETS: dict[tuple[str, str], list[PresetMatch]] = {
    # CH340 — used by all SO-ARM family kits + many generic feetech rigs.
    ("1a86", "7523"): [
        PresetMatch("so_arm101", "feetech", "family_match"),
        PresetMatch("so_arm101_leader", "feetech", "family_match"),
        PresetMatch("koch_arm", "feetech", "family_match"),
    ],
    # FT232H — alternative feetech bus.
    ("0403", "6014"): [
        PresetMatch("aloha2", "feetech", "family_match"),
    ],
    # RealSense D435 / D455.
    ("8086", "0b07"): [PresetMatch("scanrig_realsense", "realsense", "exact_match")],
    ("8086", "0b3a"): [PresetMatch("scanrig_realsense", "realsense", "exact_match")],
}


def lookup_by_vid_pid(*, vid: str | None, pid: str | None) -> list[PresetMatch]:
    if vid is None or pid is None:
        return []
    return list(_VID_PID_TO_PRESETS.get((vid.lower(), pid.lower()), []))
