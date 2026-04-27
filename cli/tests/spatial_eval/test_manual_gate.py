from __future__ import annotations

from pathlib import Path

from robot_md.spatial_eval.execute.manual_gate import (
    flag_for_review,
    list_pending_reviews,
    resolve_review,
)


def test_flag_and_resolve(tmp_path: Path):
    flag_for_review(
        run_dir=tmp_path,
        trial_id="o1-trial-3",
        video_path=tmp_path / "trial.mp4",
        auto_outcome={"target_retrieved": True, "occluder_disturbance_pct": 4.8},
        confidence=0.4,
        threshold=0.6,
    )
    pending = list_pending_reviews(tmp_path)
    assert len(pending) == 1
    assert pending[0]["trial_id"] == "o1-trial-3"

    resolve_review(tmp_path, trial_id="o1-trial-3", verdict_passed=True, reviewer="craig")
    assert list_pending_reviews(tmp_path) == []
