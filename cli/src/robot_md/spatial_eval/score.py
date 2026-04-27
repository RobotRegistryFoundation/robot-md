from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PerUnitProbeScore:
    score: float
    n: int
    passed: int


@dataclass(frozen=True)
class PerUnitExecuteScore:
    passed: int
    n: int
    evidence_sha256: str


@dataclass(frozen=True)
class ProbeTrack:
    baseline_claude: dict[str, PerUnitProbeScore]
    robot_declared: dict[str, PerUnitProbeScore]
    delta_per_unit: dict[str, float]


ExecuteTrack = dict[str, PerUnitExecuteScore]


@dataclass(frozen=True)
class Aggregate:
    probe_baseline: float
    probe_declared: float
    execute: float

    @classmethod
    def compute(cls, *, probe: ProbeTrack, execute: ExecuteTrack) -> Aggregate:
        def _mean(d: dict[str, PerUnitProbeScore]) -> float:
            return sum(v.score for v in d.values()) / max(1, len(d))
        ex_mean = (
            sum(v.passed / max(1, v.n) for v in execute.values()) / max(1, len(execute))
            if execute else 0.0
        )
        return cls(
            probe_baseline=_mean(probe.baseline_claude),
            probe_declared=_mean(probe.robot_declared),
            execute=ex_mean,
        )


@dataclass
class ScoreJSON:
    spec_version: str
    rrn: str
    run_id: str
    timestamp: str
    tracks_probe: ProbeTrack
    tracks_execute: ExecuteTrack
    aggregate: Aggregate
    rcan_signature: str | None = None
    evidence_root: str | None = None

    def to_dict(self) -> dict:
        def _dump_unit_map(m: dict) -> dict:
            return {k: asdict(v) for k, v in m.items()}
        return {
            "spec_version": self.spec_version,
            "rrn": self.rrn,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "tracks": {
                "probe": {
                    "baseline_claude": _dump_unit_map(self.tracks_probe.baseline_claude),
                    "robot_declared": _dump_unit_map(self.tracks_probe.robot_declared),
                    "delta_per_unit": dict(self.tracks_probe.delta_per_unit),
                },
                "execute": _dump_unit_map(self.tracks_execute),
            },
            "aggregate": asdict(self.aggregate),
            "rcan_signature": self.rcan_signature,
            "evidence_root": self.evidence_root,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, blob: str) -> ScoreJSON:
        d = json.loads(blob)
        def _load_probe(m: dict) -> dict[str, PerUnitProbeScore]:
            return {k: PerUnitProbeScore(**v) for k, v in m.items()}
        def _load_exec(m: dict) -> dict[str, PerUnitExecuteScore]:
            return {k: PerUnitExecuteScore(**v) for k, v in m.items()}
        return cls(
            spec_version=d["spec_version"],
            rrn=d["rrn"],
            run_id=d["run_id"],
            timestamp=d["timestamp"],
            tracks_probe=ProbeTrack(
                baseline_claude=_load_probe(d["tracks"]["probe"]["baseline_claude"]),
                robot_declared=_load_probe(d["tracks"]["probe"]["robot_declared"]),
                delta_per_unit=dict(d["tracks"]["probe"]["delta_per_unit"]),
            ),
            tracks_execute=_load_exec(d["tracks"]["execute"]),
            aggregate=Aggregate(**d["aggregate"]),
            rcan_signature=d.get("rcan_signature"),
            evidence_root=d.get("evidence_root"),
        )
