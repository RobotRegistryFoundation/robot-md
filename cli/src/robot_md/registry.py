"""Robot-md actuator catalog — fetch, score, format.

Catalog data is a single static JSON served at robotmd.dev. We keep a local
cache so `--offline` works and so HTTP hiccups degrade gracefully.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_CATALOG_URL = "https://robotmd.dev/actuators/index.json"
DEFAULT_CACHE_PATH = Path.home() / ".cache" / "robot-md" / "registry-index.json"


def fetch_index(
    *,
    url: str = DEFAULT_CATALOG_URL,
    cache_path: Path = DEFAULT_CACHE_PATH,
    offline: bool = False,
    timeout: float = 10.0,
) -> dict:
    """Fetch the catalog JSON, with offline cache fallback.

    - offline=True: read cache only. Raises FileNotFoundError if cache absent.
    - offline=False: fetch fresh, write to cache, return parsed JSON. On HTTP
      failure, fall back to cache (raises FileNotFoundError if no cache).
    """
    if offline:
        return json.loads(cache_path.read_text())
    try:
        with urlopen(url, timeout=timeout) as resp:
            body = resp.read()
        payload = json.loads(body.decode())
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2))
        return payload
    except (URLError, OSError, json.JSONDecodeError):
        return json.loads(cache_path.read_text())


def extract_manifest_signals(manifest: dict) -> list[str]:
    """Pull all driver IDs, driver models, and camera driver_ids from a
    parsed ROBOT.md manifest. Used as the LHS for catalog scoring."""
    sigs: list[str] = []
    for d in manifest.get("drivers", []) or []:
        if isinstance(d, dict):
            for k in ("id", "model"):
                v = d.get(k)
                if v:
                    sigs.append(str(v))
    physics = manifest.get("physics") or {}
    solver = physics.get("solver") or {}
    for cam in solver.get("cameras", []) or []:
        if isinstance(cam, dict):
            v = cam.get("driver_id")
            if v:
                sigs.append(str(v))
    return sigs


def _tokens(text: str) -> set[str]:
    """Tokenize text by lowercasing and splitting on whitespace, dash, underscore."""
    return {t.lower() for t in text.replace("-", " ").replace("_", " ").split() if t}


def score_entry(
    entry: dict,
    *,
    query: str,
    manifest_signals: list[str] | None,
) -> float:
    """Score an entry's relevance to a query + manifest. Range [0.0, 1.0]."""
    entry_signals = {s.lower() for s in entry.get("manifest_signals", []) or []}
    entry_tag_tokens: set[str] = set()
    for t in entry.get("hardware_tags", []) or []:
        entry_tag_tokens |= _tokens(str(t))
    desc = (entry.get("description") or "").lower()
    q_tokens = _tokens(query)

    if manifest_signals is None:
        sig_score = None
    else:
        ms_lower = {s.lower() for s in manifest_signals}
        sig_score = 1.0 if entry_signals & ms_lower else 0.0

    tag_score = 1.0 if entry_tag_tokens & q_tokens else 0.0

    desc_score = 1.0 if (q_tokens and any(t in desc for t in q_tokens)) else 0.0

    if sig_score is None:
        return tag_score * 0.75 + desc_score * 0.25
    return sig_score * 0.6 + tag_score * 0.3 + desc_score * 0.1


def format_search_results(
    scored: list[tuple[dict, float]],
    *,
    threshold: float = 0.3,
    limit: int = 5,
) -> str:
    """Render top-N entries with their scores. Below-threshold entries are
    still printed but tagged as weak. Empty list prints the no-match guidance.
    """
    if not scored:
        return (
            "No matches found. Ask Claude Code to write one, then "
            "'robot-md actuator publish' so the next person finds it.\n"
        )
    lines: list[str] = []
    for entry, score in scored[:limit]:
        name = entry.get("name", "?")
        version = entry.get("version", "")
        desc = entry.get("description", "")
        weak = "  (weak match — consider writing a new actuator)" if score < threshold else ""
        lines.append(f"{score:0.2f}  {name} {version}{weak}")
        lines.append(f"        {desc}")
        plugin = entry.get("plugin_marketplace_entry")
        if plugin and plugin.get("install_command"):
            lines.append(f"        $ {plugin['install_command']}")
        else:
            install = entry.get("install") or {}
            pm = install.get("package_manager", "pip")
            pkg = install.get("package", name)
            post = install.get("post_install")
            cmd = f"{pm} install {pkg}"
            if post:
                cmd += f" && {post}"
            lines.append(f"        $ {cmd}")
        lines.append("")
    return "\n".join(lines)
