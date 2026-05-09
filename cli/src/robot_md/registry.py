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
