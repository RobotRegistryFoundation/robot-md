from __future__ import annotations
import json
import os
from typing import Protocol


class Stack(Protocol):
    def answer(self, probe: dict) -> dict: ...


class FakeStack:
    """Deterministic stack used by tests. Maps probe id -> answer dict."""

    def __init__(self, answers: dict[str, dict]) -> None:
        self._answers = answers

    def answer(self, probe: dict) -> dict:
        pid = probe["id"]
        if pid not in self._answers:
            raise KeyError(f"FakeStack has no canned answer for {pid!r}")
        return self._answers[pid]


class BaselineClaudeStack:
    """Calls Anthropic SDK. Lazy client construction so tests can resolve_stack
    without ANTHROPIC_API_KEY in the environment.
    """

    def __init__(self, model: str) -> None:
        self.model = model
        self._client = None

    def _client_now(self):
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def answer(self, probe: dict) -> dict:
        client = self._client_now()
        # System prompt cached; per-probe content is the variable part.
        system_blocks = [
            {"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
        ]
        user_content = [
            {"type": "text", "text": probe["scenario_header"]},
            *_frames_as_content(probe.get("frames", [])),
            {"type": "text", "text": json.dumps(probe["question"])},
        ]
        msg = client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_blocks,
            messages=[{"role": "user", "content": user_content}],
        )
        # Expect a single text block with JSON body.
        text = "".join(b.text for b in msg.content if b.type == "text")
        return json.loads(text)


_SYSTEM_PROMPT = """You are evaluating spatial-intelligence probes for an embodied robot benchmark.
Each probe asks a structured question about a scene. Respond with ONE JSON object matching the
question's required shape, no prose, no markdown fence."""


def _frames_as_content(frames: list[str]) -> list[dict]:
    out = []
    for f in frames:
        out.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": f}})
    return out


def resolve_stack(identifier: str) -> Stack:
    if not identifier.startswith("claude:"):
        raise ValueError(f"v1 supports only 'claude:<model>' identifiers; got {identifier!r}")
    model = identifier.split(":", 1)[1]
    return BaselineClaudeStack(model)
