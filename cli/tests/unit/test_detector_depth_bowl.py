"""Depth-first detector for bowl/cylinder/plane shapes."""
from __future__ import annotations

import numpy as np

from robot_md.detectors.depth import detect_depth_shape


def _flat_table_depth(shape=(400, 600)):
    """Flat table at z=500mm."""
    return np.full(shape, 500, dtype=np.uint16)


def _table_with_bowl(shape=(400, 600), center=(300, 200), radius=40, depth_table=500, depth_rim=470):
    """A round bowl-shaped depression on a table — rim (ring) closer than table, interior clear."""
    d = _flat_table_depth(shape)
    yy, xx = np.ogrid[: shape[0], : shape[1]]
    dist = np.hypot(xx - center[0], yy - center[1])
    ring = (dist >= radius - 5) & (dist <= radius)
    d[ring] = depth_rim
    return d


def test_bowl_detected_on_table():
    depth = _table_with_bowl()
    K = np.array([[600, 0, 300], [0, 600, 200], [0, 0, 1]], dtype=float)
    # z_range narrowed to [460, 490] so only the rim (470mm) is in-band,
    # not the table (500mm).  This makes the connected component ~80px wide →
    # diameter ≈ 67mm, which falls in [40, 150].
    result = detect_depth_shape(
        depth,
        K,
        params={"shape": "bowl", "min_diameter_mm": 40, "max_diameter_mm": 150, "z_range_mm": [460, 490]},
    )
    assert result is not None
    u, v, _area = result
    assert 250 < u < 350
    assert 150 < v < 250


def test_no_bowl_when_only_flat_table():
    depth = _flat_table_depth()
    K = np.array([[600, 0, 300], [0, 600, 200], [0, 0, 1]], dtype=float)
    result = detect_depth_shape(
        depth,
        K,
        params={"shape": "bowl", "min_diameter_mm": 40, "max_diameter_mm": 150, "z_range_mm": [400, 520]},
    )
    assert result is None


def test_z_range_excludes_out_of_workspace_objects():
    """An object at 8000mm (wall) must not be detected when z_range excludes it."""
    depth = np.full((400, 600), 8000, dtype=np.uint16)
    K = np.array([[600, 0, 300], [0, 600, 200], [0, 0, 1]], dtype=float)
    result = detect_depth_shape(
        depth,
        K,
        params={"shape": "bowl", "min_diameter_mm": 40, "max_diameter_mm": 150, "z_range_mm": [400, 520]},
    )
    assert result is None
