"""Tests for publisher key auto-mint + load."""

from __future__ import annotations

import pytest

from robot_md.publisher_key import (
    KeyPair,
    load_or_mint_publisher_key,
    publisher_key_dir,
)


def test_publisher_key_dir_under_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    d = publisher_key_dir("alice")
    assert d == tmp_path / ".robot-md" / "publisher-keys" / "alice"


def test_load_or_mint_creates_keypair_on_first_call(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    kp = load_or_mint_publisher_key("alice")
    assert isinstance(kp, KeyPair)
    assert kp.pq_kid == "publisher-alice"
    assert (tmp_path / ".robot-md" / "publisher-keys" / "alice" / "ed25519.bin").is_file()
    assert (tmp_path / ".robot-md" / "publisher-keys" / "alice" / "ml-dsa.bin").is_file()


def test_load_or_mint_returns_same_keypair_on_second_call(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    kp1 = load_or_mint_publisher_key("alice")
    kp2 = load_or_mint_publisher_key("alice")
    assert kp1.pq_signing_pub == kp2.pq_signing_pub
    assert kp1.ed25519_pub == kp2.ed25519_pub
    assert kp1.ed25519_sec == kp2.ed25519_sec


def test_different_users_get_different_keypairs(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = load_or_mint_publisher_key("alice")
    b = load_or_mint_publisher_key("bob")
    assert a.pq_signing_pub != b.pq_signing_pub


def test_keypair_has_all_signing_inputs():
    """Smoke: KeyPair carries everything sign_envelope needs."""
    from rcan import MlDsaKeyPair

    kp = KeyPair(
        pq_kid="x",
        pq_signing_pub=b"a",
        pq_signing_sec=b"b",
        ed25519_pub=b"c",
        ed25519_sec=b"d",
        ml_dsa=MlDsaKeyPair(key_id="x", public_key_bytes=b"a", _secret_key=b"b"),
    )
    assert kp.pq_kid == "x"


def test_load_or_mint_rejects_empty_username(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ValueError):
        load_or_mint_publisher_key("")
