"""Hot-plug event tier classifier."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from robot_md.backends import BackendRegistry
from robot_md.backends.capability import Capability
from robot_md.hotplug import presets_index
from robot_md.hotplug.event import DeviceEvent

_RECENT_REJECT_WINDOW = timedelta(hours=1)


def _recent_reject_for(evt: DeviceEvent) -> str | None:
    """Return the ISO timestamp of the most-recent reject for this device, or None.

    Default implementation returns None until Task 9 wires the queue file in.
    Tests patch this to inject fixtures.
    """
    return None


@dataclass(frozen=True)
class BindProposal:
    rrn: str | None
    driver_id_suggestion: str
    backend_name: str
    preset_name: str | None
    capability_preview: list[Capability]
    inferred_fields: dict


@dataclass(frozen=True)
class Decision:
    tier: Literal["HIGH", "MEDIUM", "LOW"]
    unambiguous: bool
    bind_proposal: BindProposal | None
    alternatives: list[BindProposal] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _installed_backends_for_transport(transport: str) -> list[str]:
    """Return names of installed backends whose .protocols set includes transport."""
    reg = BackendRegistry.from_entry_points()
    return sorted(b.name for b in reg.backends if transport in b.protocols)


def classify(evt: DeviceEvent) -> Decision:
    """Tier-classify a hot-plug event.

    HIGH:   single preset match (typically via VID:PID:serial triple) AND
            exactly one matching backend installed → auto-bind.
    MEDIUM: multi-preset match OR multi-backend match. Top-1 candidate +
            alternatives surfaced; queued.
    LOW:    no preset match OR known transport with no backend installed.
    """
    preset_matches = presets_index.lookup_by_vid_pid(vid=evt.vid, pid=evt.pid)
    if not preset_matches:
        return Decision(
            tier="LOW",
            unambiguous=False,
            bind_proposal=None,
            alternatives=[],
            reasons=[f"no preset match for VID:PID {evt.vid}:{evt.pid}"],
        )

    backends = _installed_backends_for_transport(evt.transport)
    if not backends:
        return Decision(
            tier="LOW",
            unambiguous=False,
            bind_proposal=None,
            alternatives=[],
            reasons=[
                f"no backend installed for transport {evt.transport!r}",
                "hint: pip install 'robot-md[hardware]'",
            ],
        )

    proposals: list[BindProposal] = []
    for pm in preset_matches:
        for backend_name in backends:
            proposals.append(
                BindProposal(
                    rrn=None,
                    driver_id_suggestion="arm_servos",
                    backend_name=backend_name,
                    preset_name=pm.preset_name,
                    capability_preview=[],
                    inferred_fields={
                        "port": evt.path,
                        "transport": evt.transport,
                        "serial": evt.serial,
                    },
                )
            )

    if len(proposals) == 1 and preset_matches[0].confidence == "exact_match":
        recent = _recent_reject_for(evt)
        if recent is not None:
            recent_dt = datetime.fromisoformat(recent.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - recent_dt < _RECENT_REJECT_WINDOW:
                return Decision(
                    tier="MEDIUM",
                    unambiguous=False,
                    bind_proposal=proposals[0],
                    alternatives=[],
                    reasons=[
                        f"exact preset match {preset_matches[0].preset_name}",
                        f"recently rejected at {recent}; not auto-binding",
                    ],
                )
        return Decision(
            tier="HIGH",
            unambiguous=True,
            bind_proposal=proposals[0],
            alternatives=[],
            reasons=[
                f"exact preset match {preset_matches[0].preset_name}",
                f"single backend installed: {backends[0]}",
            ],
        )

    return Decision(
        tier="MEDIUM",
        unambiguous=False,
        bind_proposal=proposals[0],
        alternatives=proposals[1:],
        reasons=[
            f"VID:PID matches {len(preset_matches)} preset(s)",
            f"{len(backends)} backend(s) could drive this transport",
        ],
    )
