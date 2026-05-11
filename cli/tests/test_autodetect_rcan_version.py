import yaml
from robot_md.autodetect import Scan, emit_draft


def test_emit_draft_uses_current_rcan_version():
    """The init draft must match the current canonical RCAN spec version."""
    # Pin to the canonical version. When rcan-py bumps, this test forces a
    # template review — drift is intentional friction.
    expected = "3.2"
    draft = emit_draft(Scan())
    fm_block = draft.split("---\n", 2)[1]  # frontmatter between --- markers
    fm = yaml.safe_load(fm_block)
    assert fm["rcan_version"] == expected, (
        f"rcan_version template drift: emitted {fm['rcan_version']!r}, "
        f"expected {expected!r}. Bump the template literal in autodetect.py."
    )
