"""Smoke test for the actuator catalog page. Parses the static HTML and
verifies it embeds the JSON-loading JS, an empty-state, and a results
container. Marked slow because it does real file I/O outside cli/."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HTML = REPO_ROOT / "site" / "actuators" / "index.html"


@pytest.mark.slow
def test_actuator_catalog_html_exists():
    assert HTML.is_file(), f"missing: {HTML}"


@pytest.mark.slow
def test_actuator_catalog_html_embeds_loader():
    src = HTML.read_text()
    # Must fetch the sibling JSON.
    assert "index.json" in src, "expected fetch of sibling index.json"
    # Must render an entry list container the JS targets.
    assert 'id="entries"' in src or "id='entries'" in src
    # Must render an empty state.
    assert "No actuators published yet" in src
    # Must render a fuzzy filter input.
    assert 'id="filter"' in src or "id='filter'" in src
    # Must mention plugin badge for plugin_marketplace_entry case.
    assert "plugin install" in src.lower()
