"""Hot-plug daemon config loaded from ~/.robot-md/hotplug.toml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib  # py3.11+
except ImportError:
    import tomli as tomllib  # type: ignore


_DEFAULT_PATH = Path.home() / ".robot-md" / "hotplug.toml"


@dataclass(frozen=True)
class HotplugConfig:
    pending_ttl_days: float = 7.0

    @classmethod
    def load(cls, *, path: Path = _DEFAULT_PATH) -> HotplugConfig:
        if not path.exists():
            return cls()
        data = tomllib.loads(path.read_text())
        return cls(pending_ttl_days=float(data.get("pending_ttl_days", 7.0)))
