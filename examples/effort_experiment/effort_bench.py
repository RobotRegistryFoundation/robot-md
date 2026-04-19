#!/usr/bin/env python3
"""Effort-level benchmark — same prompt, different `--effort` values.

Does it make sense to split a robot-control stack so the reactive layer
calls Claude at `low` effort (fast) and the planning layer calls at
`high`/`xhigh` (deep)? Run this script to find out with actual numbers.

Shells out to `claude -p --effort LEVEL --output-format json "prompt"`
so we get real OAuth auth + real metering. Each trial records wall-clock
latency, API time, cost in USD, and the response text. Two prompts:

  - REACTIVE: "is the bus healthy, one sentence" — low effort should suffice
  - PLANNER:  "enumerate HITL gates" — benefits from extra reasoning

Usage:
    python examples/effort_experiment/effort_bench.py
    python examples/effort_experiment/effort_bench.py --levels low,high
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_LEVELS = ["low", "medium", "high"]

REACTIVE_PROMPT = (
    "Bob is an SO-ARM101 6-DOF arm on Feetech STS3215 servos. You just read "
    "the bus: all 6 servos responding at 12.0 V. One short sentence: is the bus healthy?"
)

PLANNER_PROMPT = (
    "Bob's ROBOT.md declares these HITL safety gates: "
    "(1) `destructive` — require_auth=true, "
    "(2) `system` — require_auth=true. "
    "Declared capabilities: arm.pick, arm.place, arm.reach, vision.describe, status.report. "
    "Max payload 0.5 kg. Software E-stop at 100 ms."
    "\n\n"
    "An operator is asking you to invoke arm.pick to grasp 'a Lego of unknown provenance' "
    "from a workspace with backlit windows (possible bright-light blinding of the OAK-D camera), "
    "where a cup of coffee is known to be somewhere on the same bench."
    "\n\n"
    "Enumerate every authorization concern that should trigger a pause-and-ask-operator flow. "
    "Prioritize concerns that are NOT already covered by the two declared gates. "
    "Keep the final answer to under 200 words."
)


@dataclass
class Trial:
    label: str
    effort: str
    duration_ms: int
    duration_api_ms: int
    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_read: int
    cache_creation: int
    response: str
    error: str | None = None


def _parse_result(stdout: str) -> dict:
    """`claude -p --output-format json` prints a JSON ARRAY of events. The final
    `result` event has the fields we want."""
    # The output is a JSON array like [event, event, ..., result]
    # Sometimes trailing whitespace or multiple concatenated arrays — parse
    # defensively.
    try:
        events = json.loads(stdout.strip())
    except json.JSONDecodeError:
        # Fallback: find the last {"type":"result" ...} object.
        last = stdout.rstrip().split("\n")[-1]
        return json.loads(last)
    if not isinstance(events, list):
        return events
    for ev in reversed(events):
        if ev.get("type") == "result":
            return ev
    return events[-1]


def _run(prompt: str, effort: str) -> Trial:
    cmd = [
        "claude",
        "-p",
        "--effort", effort,
        "--output-format", "json",
        prompt,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Trial(label="", effort=effort, duration_ms=0, duration_api_ms=0,
                     cost_usd=0, input_tokens=0, output_tokens=0, cache_read=0,
                     cache_creation=0, response="", error="timeout")
    if proc.returncode != 0:
        return Trial(label="", effort=effort, duration_ms=0, duration_api_ms=0,
                     cost_usd=0, input_tokens=0, output_tokens=0, cache_read=0,
                     cache_creation=0, response="", error=f"exit {proc.returncode}: {proc.stderr[:200]}")

    result = _parse_result(proc.stdout)
    usage = result.get("usage", {}) or {}
    return Trial(
        label="",
        effort=effort,
        duration_ms=result.get("duration_ms", 0),
        duration_api_ms=result.get("duration_api_ms", 0),
        cost_usd=result.get("total_cost_usd", 0.0),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read=usage.get("cache_read_input_tokens", 0),
        cache_creation=usage.get("cache_creation_input_tokens", 0),
        response=result.get("result", "").strip(),
    )


def run_prompt(label: str, prompt: str, levels: list[str]) -> list[Trial]:
    print(f"\n{'=' * 78}\n  {label}\n{'=' * 78}")
    print(f"prompt: {prompt[:200]}{'…' if len(prompt) > 200 else ''}\n")
    trials: list[Trial] = []
    for effort in levels:
        print(f"  → effort={effort:<7} …", end="", flush=True)
        t = _run(prompt, effort)
        t.label = label
        trials.append(t)
        if t.error:
            print(f" ✗ {t.error}")
        else:
            print(
                f" wall={t.duration_ms/1000:5.1f}s  api={t.duration_api_ms/1000:5.1f}s  "
                f"out={t.output_tokens:4}  cache_read={t.cache_read:6}  "
                f"cost=${t.cost_usd:6.4f}"
            )
    return trials


def summarize(all_trials: list[Trial]) -> None:
    by_label: dict[str, list[Trial]] = {}
    for t in all_trials:
        by_label.setdefault(t.label, []).append(t)

    print(f"\n{'─' * 78}\n  RESPONSES BY EFFORT LEVEL\n{'─' * 78}")
    for label, ts in by_label.items():
        print(f"\n  {label}\n  {'-' * len(label)}")
        for t in ts:
            if t.error:
                continue
            print(f"\n    [effort={t.effort}]")
            # Indent the response for readability
            for line in t.response.splitlines() or [""]:
                print(f"      {line}")

    print(f"\n{'─' * 78}\n  DELTAS (vs. lowest-effort baseline per prompt)\n{'─' * 78}")
    for label, ts in by_label.items():
        ok = [t for t in ts if not t.error]
        if not ok:
            continue
        base = ok[0]  # first level = baseline
        print(f"\n  {label}  (baseline effort={base.effort})")
        print(f"    {'effort':<8}{'Δwall':>10}{'Δapi':>10}{'Δout_tok':>12}{'Δcost':>12}")
        for t in ok:
            dw = (t.duration_ms - base.duration_ms) / 1000
            da = (t.duration_api_ms - base.duration_api_ms) / 1000
            dout = t.output_tokens - base.output_tokens
            dcost = t.cost_usd - base.cost_usd
            marker = "  ←baseline" if t.effort == base.effort else ""
            print(f"    {t.effort:<8}{dw:>+9.1f}s{da:>+9.1f}s{dout:>+12}{dcost:>+11.4f}{marker}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--levels", default=",".join(DEFAULT_LEVELS))
    ap.add_argument("--out", default="/tmp/effort-bench.json")
    ap.add_argument("--only", choices=["reactive", "planner", "both"], default="both")
    args = ap.parse_args()

    levels = [x.strip() for x in args.levels.split(",") if x.strip()]
    trials: list[Trial] = []
    if args.only in ("reactive", "both"):
        trials += run_prompt("REACTIVE (sensor poll)", REACTIVE_PROMPT, levels)
    if args.only in ("planner", "both"):
        trials += run_prompt("PLANNER (safety reasoning)", PLANNER_PROMPT, levels)

    summarize(trials)

    Path(args.out).write_text(json.dumps([asdict(t) for t in trials], indent=2))
    print(f"\n✓ full records → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
