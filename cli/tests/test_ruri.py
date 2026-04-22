"""v0.9.1 — RURI construction tests."""

from __future__ import annotations

import pytest

from robot_md.ruri import construct_ruri, slug


def test_slug_lowercase_alphanum_and_hyphen():
    assert slug("Bob The Robot") == "bob-the-robot"


def test_slug_strips_special_chars():
    assert slug("SO-ARM/101 v2.0!") == "so-arm-101-v2-0"


def test_slug_collapses_repeated_hyphens():
    assert slug("a--b---c") == "a-b-c"


def test_slug_strips_leading_trailing_hyphens():
    assert slug("-hello-") == "hello"


def test_slug_empty_raises():
    with pytest.raises(ValueError):
        slug("!!!")


def test_construct_ruri_uses_explicit_metadata_ruri_if_set():
    m = {
        "metadata": {
            "ruri": "rcan://custom/host/arm/a1",
            "robot_name": "x",
            "manufacturer": "y",
            "model": "z",
        }
    }
    assert construct_ruri(m) == "rcan://custom/host/arm/a1"


def test_construct_ruri_defaults_to_robotregistryfoundation_host():
    m = {"metadata": {"robot_name": "Bob", "manufacturer": "Acme", "model": "T1"}}
    r = construct_ruri(m)
    assert r == "rcan://robotregistryfoundation.org/acme/t1/bob"


def test_construct_ruri_slugifies_all_parts():
    m = {"metadata": {"robot_name": "Robo Bot!", "manufacturer": "Acme Co.", "model": "T 1"}}
    r = construct_ruri(m)
    assert r == "rcan://robotregistryfoundation.org/acme-co/t-1/robo-bot"


def test_construct_ruri_missing_field_raises():
    m = {"metadata": {"robot_name": "x", "manufacturer": "y"}}  # no model
    with pytest.raises(ValueError):
        construct_ruri(m)
