from __future__ import annotations

import pytest

from robot_md.backends.registry import (
    BackendRegistrationError,
    _validate_capability_namespace,
)


@pytest.mark.parametrize(
    "bad_capability",
    [
        "pick",        # no namespace
        "Arm.pick",    # uppercase
        "arm-pick",    # hyphen
        ".arm.pick",   # leading dot
        "arm.",        # trailing dot
        "1arm.pick",   # leading digit
        "arm. pick",   # whitespace
    ],
)
def test_malformed_capability_rejected(bad_capability: str) -> None:
    with pytest.raises(BackendRegistrationError) as excinfo:
        _validate_capability_namespace("bad_backend", frozenset({bad_capability}))
    assert "bad_backend" in str(excinfo.value)
    assert bad_capability in str(excinfo.value)
