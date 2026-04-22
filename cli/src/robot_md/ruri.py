"""RURI construction for robot-md register.

Spec-mandated format: rcan://<registry-host>/<manufacturer>/<model>/<device-id>.
robot-md v0.9.1 defaults <registry-host> to robotregistryfoundation.org.
"""

from __future__ import annotations

import re
from typing import Any

REGISTRY_HOST = "robotregistryfoundation.org"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(s: str) -> str:
    """Lowercase, alphanumeric-or-hyphen, collapse repeats, strip ends.

    Raises ValueError if the result is empty (all non-alphanumeric input).
    """
    out = _SLUG_RE.sub("-", s.lower()).strip("-")
    if not out:
        raise ValueError(f"cannot slugify {s!r} — no alphanumeric characters")
    return out


def construct_ruri(manifest: dict[str, Any]) -> str:
    """Return the RURI for this manifest.

    If metadata.ruri is explicitly set, return it verbatim.
    Otherwise build rcan://{REGISTRY_HOST}/{slug(manufacturer)}/{slug(model)}/{slug(robot_name)}.
    """
    meta = manifest.get("metadata") or {}
    explicit = (meta.get("ruri") or "").strip()
    if explicit:
        return explicit

    for k in ("robot_name", "manufacturer", "model"):
        if not meta.get(k):
            raise ValueError(f"cannot construct RURI: metadata.{k} missing")

    return (
        f"rcan://{REGISTRY_HOST}"
        f"/{slug(meta['manufacturer'])}"
        f"/{slug(meta['model'])}"
        f"/{slug(meta['robot_name'])}"
    )
