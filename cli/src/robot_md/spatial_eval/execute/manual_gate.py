from __future__ import annotations

import json
from pathlib import Path


def flag_for_review(
    *,
    run_dir: Path,
    trial_id: str,
    video_path: Path,
    auto_outcome: dict,
    confidence: float,
    threshold: float,
) -> None:
    pending = run_dir / "pending_review"
    pending.mkdir(parents=True, exist_ok=True)
    (pending / f"{trial_id}.json").write_text(
        json.dumps(
            {
                "trial_id": trial_id,
                "video_path": str(video_path),
                "auto_outcome": auto_outcome,
                "confidence": confidence,
                "threshold": threshold,
            },
            indent=2,
        )
    )


def list_pending_reviews(run_dir: Path) -> list[dict]:
    pending = run_dir / "pending_review"
    if not pending.is_dir():
        return []
    return [json.loads(p.read_text()) for p in sorted(pending.glob("*.json"))]


def resolve_review(
    run_dir: Path, *, trial_id: str, verdict_passed: bool, reviewer: str
) -> None:
    pending = run_dir / "pending_review"
    f = pending / f"{trial_id}.json"
    if not f.is_file():
        raise FileNotFoundError(f"no pending review for {trial_id}")
    record = json.loads(f.read_text())
    record["resolved"] = {"passed": verdict_passed, "reviewer": reviewer}
    resolved = run_dir / "resolved_review"
    resolved.mkdir(parents=True, exist_ok=True)
    (resolved / f"{trial_id}.json").write_text(json.dumps(record, indent=2))
    f.unlink()
