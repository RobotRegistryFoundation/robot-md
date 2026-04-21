"""Preset scoring must break the so_arm101 vs so_arm101_leader tie."""

from __future__ import annotations

from robot_md.init import Preset, match_score, pick_best


class _Dev:
    def __init__(self, bus, protocol, label="", path=None):
        self.bus = bus
        self.protocol = protocol
        self.label = label
        self.path = path


class _Scan:
    def __init__(self, devices):
        self.devices = devices


def _follower():
    return Preset(
        name="so_arm101",
        match={
            "drivers": {"protocol": "feetech", "count": 6},
            "negative_hints": ["leader"],
        },
        data={},
    )


def _leader():
    return Preset(
        name="so_arm101_leader",
        match={
            "drivers": {"protocol": "feetech", "count": 6},
            "name_hints": ["leader"],
        },
        data={},
    )


def test_count_bonus_applies_when_servo_count_matches():
    scan = _Scan(
        [
            _Dev("probe", "feetech", "Feetech bus on /dev/ttyACM0 (6 servos)", "/dev/ttyACM0"),
        ]
    )
    r = match_score(_follower(), scan)
    # +10 protocol, +5 count match, no leader label => 15
    assert r.score == 15
    assert any("count" in reason for reason in r.reasons)


def test_count_mismatch_does_not_subtract():
    scan = _Scan(
        [_Dev("probe", "feetech", "Feetech bus on /dev/ttyACM0 (2 servos)", "/dev/ttyACM0")]
    )
    r = match_score(_follower(), scan)
    # +10 protocol, count mismatch is 0 (not negative), no leader => 10
    assert r.score == 10


def test_negative_hint_subtracts():
    scan = _Scan(
        [
            _Dev(
                "probe",
                "feetech",
                "Feetech leader bus on /dev/ttyACM0 (6 servos)",
                "/dev/ttyACM0",
            )
        ]
    )
    follower = match_score(_follower(), scan)
    leader = match_score(_leader(), scan)
    # follower: +10 protocol, +5 count, -5 "leader" label => 10
    # leader:   +10 protocol, +5 count                   => 15
    assert follower.score == 10
    assert leader.score == 15


def test_pick_best_prefers_follower_on_non_leader_rig():
    scan = _Scan(
        [_Dev("probe", "feetech", "Feetech bus on /dev/ttyACM0 (6 servos)", "/dev/ttyACM0")]
    )
    presets = [_leader(), _follower()]  # order-independent
    chosen = pick_best(presets, scan)
    assert chosen is not None
    assert chosen.preset.name == "so_arm101"


def test_pick_best_prefers_leader_on_leader_rig():
    scan = _Scan(
        [
            _Dev(
                "probe",
                "feetech",
                "Feetech leader bus on /dev/ttyACM0 (6 servos)",
                "/dev/ttyACM0",
            )
        ]
    )
    presets = [_follower(), _leader()]
    chosen = pick_best(presets, scan)
    assert chosen is not None
    assert chosen.preset.name == "so_arm101_leader"


def test_hostname_leader_flips_pick_to_leader(monkeypatch):
    """On a host whose HOSTNAME contains 'leader' but whose device label
    does NOT, so_arm101_leader wins: +10 protocol +5 count +3 hostname
    = 18, vs so_arm101 at +10 +5 +0 = 15 (no 'leader' in label, so
    negative_hints is silent)."""
    monkeypatch.setattr(
        "socket.gethostname",
        lambda: "leader-bench-01",
    )
    scan = _Scan(
        [_Dev("probe", "feetech", "Feetech bus on /dev/ttyACM0 (6 servos)", "/dev/ttyACM0")]
    )
    follower = match_score(_follower(), scan)
    leader = match_score(_leader(), scan)
    assert follower.score == 15
    assert leader.score == 18
    assert pick_best([_follower(), _leader()], scan).preset.name == "so_arm101_leader"


def test_alphabetical_tiebreak_is_deterministic(monkeypatch):
    """With both presets scoring identically on a canonical follower rig
    (no 'leader' in label or hostname), the alphabetical tiebreak
    returns so_arm101 regardless of input order."""
    monkeypatch.setattr("socket.gethostname", lambda: "bench-01")
    scan = _Scan(
        [_Dev("probe", "feetech", "Feetech bus on /dev/ttyACM0 (6 servos)", "/dev/ttyACM0")]
    )
    a = pick_best([_follower(), _leader()], scan)
    b = pick_best([_leader(), _follower()], scan)
    assert a.preset.name == b.preset.name == "so_arm101"
