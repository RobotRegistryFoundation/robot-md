"""Public backend API.

Re-exports CapabilityBackend, BackendRegistry, Capability, and the
enumerate_capabilities walker.
"""

from __future__ import annotations

from robot_md.backends.base import CapabilityBackend, ExecutionEvent, ExecutionResult, SceneSnapshot
from robot_md.backends.capability import Capability, derive_namespace
from robot_md.backends.registry import (
    CORE_CAPABILITY_PREFIXES,
    BackendRegistrationError,
    BackendRegistry,
    discover_backends,
)


def enumerate_capabilities(registry: BackendRegistry) -> list[tuple[str, Capability]]:
    """Walk all registered backends, return (backend_name, Capability) pairs.

    Used by:
      - The `robot-md describe-capabilities` CLI subcommand (Task 8).
      - Future SP-HP daemon — preview a backend's capabilities at hot-plug time.
      - Future robot-md-http OpenAPI generator.

    Backends MAY override describe_capabilities() to provide richer metadata;
    the override is preserved here.
    """
    out: list[tuple[str, Capability]] = []
    for backend in registry.backends:
        for cap in backend.describe_capabilities():
            out.append((backend.name, cap))
    return out


__all__ = [
    "CORE_CAPABILITY_PREFIXES",
    "BackendRegistrationError",
    "BackendRegistry",
    "Capability",
    "CapabilityBackend",
    "ExecutionEvent",
    "ExecutionResult",
    "SceneSnapshot",
    "derive_namespace",
    "discover_backends",
    "enumerate_capabilities",
]
