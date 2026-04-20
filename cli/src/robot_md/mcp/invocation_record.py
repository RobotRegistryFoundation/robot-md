"""Completed-invocation record coalesced from a paired tool.call/tool.result event.

Populated by the manifest-stamping publisher wrapper in McpContext; stored in
InvocationLog; surfaced by the recent_invocations / recent_errors resources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InvocationRecord:
    timestamp: float
    tool: str
    capability: str | None
    args: dict[str, Any]
    status: str
    reason: str | None
    request_id: str
    manifest_path: str
    preconditions: list[dict] = field(default_factory=list)

    @classmethod
    def from_event_pair(cls, call_evt: dict, result_evt: dict) -> "InvocationRecord":
        call_data = call_evt.get("data", {})
        result_data = result_evt.get("data", {})

        call_rid = call_data.get("request_id")
        result_rid = result_data.get("request_id")
        if call_rid != result_rid:
            raise ValueError(
                f"request_id mismatch: call={call_rid!r} result={result_rid!r}"
            )

        err = result_data.get("error") or {}
        reason = err.get("reason") if isinstance(err, dict) else None
        preconditions = (
            list(err.get("preconditions") or []) if reason == "precondition" else []
        )

        return cls(
            timestamp=float(result_evt.get("ts", 0.0)),
            tool=call_data.get("tool", ""),
            capability=call_data.get("capability"),
            args=dict(call_data.get("args") or {}),
            status=result_data.get("status", "unknown"),
            reason=reason,
            request_id=call_rid or "",
            manifest_path=str(
                result_data.get("manifest_path") or call_data.get("manifest_path") or ""
            ),
            preconditions=preconditions,
        )
