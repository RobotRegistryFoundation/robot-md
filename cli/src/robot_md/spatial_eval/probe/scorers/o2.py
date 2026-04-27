from __future__ import annotations

from robot_md.spatial_eval.probe.scorer import register_scorer


def _score_o2(answer: dict, truth: dict) -> tuple[bool, float]:
    ok = answer.get("container") == truth.get("container") and answer.get("contained") == truth.get(
        "contained"
    )
    return (ok, 1.0 if ok else 0.0)


register_scorer("O2", _score_o2)
