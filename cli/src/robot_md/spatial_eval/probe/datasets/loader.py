from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "public"


def load_public_split() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for unit_dir in sorted(ROOT.iterdir()):
        if not unit_dir.is_dir():
            continue
        unit = unit_dir.name
        probes = []
        for p in sorted(unit_dir.glob("*.json")):
            probes.append(json.loads(p.read_text()))
        out[unit] = probes
    return out
