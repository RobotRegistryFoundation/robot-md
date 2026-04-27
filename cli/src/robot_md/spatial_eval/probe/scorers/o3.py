from __future__ import annotations

from robot_md.spatial_eval.probe.scorer import register_scorer

PASS_IOU = 0.5


def _aabb(corners: list[tuple]) -> tuple[float, float, float, float, float, float]:
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    zs = [c[2] for c in corners]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _iou(a, b) -> float:
    ax1, ay1, az1, ax2, ay2, az2 = a
    bx1, by1, bz1, bx2, by2, bz2 = b
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    iz = max(0.0, min(az2, bz2) - max(az1, bz1))
    inter = ix * iy * iz
    va = (ax2 - ax1) * (ay2 - ay1) * (az2 - az1)
    vb = (bx2 - bx1) * (by2 - by1) * (bz2 - bz1)
    union = va + vb - inter
    return 0.0 if union <= 0 else inter / union


def _score_o3(answer: dict, truth: dict) -> tuple[bool, float]:
    iou = _iou(_aabb(answer["bbox_corners"]), _aabb(truth["bbox_corners"]))
    return (iou >= PASS_IOU, iou)


register_scorer("O3", _score_o3)
