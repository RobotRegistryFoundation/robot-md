# cli/src/robot_md/backends/_capability_default.py
"""Default impl of describe_capabilities() — looks up arg_schema in capabilities.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from robot_md.backends.capability import Capability, derive_namespace

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "capabilities.json"


@lru_cache(maxsize=1)
def _load_capabilities_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text())


def describe_default(backend_name: str, caps: frozenset[str]) -> list[Capability]:
    """Build Capability objects for each capability the backend declared.

    For each capability:
      - Look up arg_schema in capabilities.json under definitions[name]; None if absent.
      - description: schema's "description" field if present, else "".
      - namespace: derive_namespace(name) — "core" or "vendor".

    Vendor capabilities NOT in capabilities.json get arg_schema=None;
    adapter authors who want richer metadata override describe_capabilities()
    on their CapabilityBackend subclass.
    """
    schema = _load_capabilities_schema()
    defs = schema.get("definitions", {})
    out: list[Capability] = []
    for cap in sorted(caps):
        entry = defs.get(cap)
        out.append(
            Capability(
                name=cap,
                namespace=derive_namespace(cap),
                arg_schema=entry,
                description=(entry or {}).get("description", "") if entry else "",
            )
        )
    return out
