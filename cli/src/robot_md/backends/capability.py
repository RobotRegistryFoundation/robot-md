# cli/src/robot_md/backends/capability.py
"""Public Capability metadata API.

See SP3 spec § Capability Metadata Addendum (2026-04-27).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from robot_md.backends.registry import CORE_CAPABILITY_PREFIXES


@dataclass(frozen=True)
class Capability:
    """Rich metadata for a capability declared by a backend.

    name        — e.g. "arm.pick", "lerobot.teleop"
    namespace   — "core" if name starts with a CORE_CAPABILITY_PREFIXES entry,
                  otherwise "vendor"
    arg_schema  — JSON-Schema fragment from capabilities.json, or None for
                  vendor capabilities not in the schema
    description — short human-readable; "" if none available
    """

    name: str
    namespace: Literal["core", "vendor"]
    arg_schema: dict | None
    description: str


def derive_namespace(capability_name: str) -> Literal["core", "vendor"]:
    """Return 'core' if the name starts with a core prefix, else 'vendor'."""
    if any(capability_name.startswith(p) for p in CORE_CAPABILITY_PREFIXES):
        return "core"
    return "vendor"
