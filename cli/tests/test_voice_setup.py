import io
from pathlib import Path
import pytest
import yaml

from robot_md.init_phases.voice_setup import run_voice_setup


def _stub_pendantd(monkeypatch, devices=None):
    """Inject a stub pendantd.audio.devices module."""
    devices = devices or {"inputs": [], "outputs": []}
    class FakeDevice:
        def __init__(self, name): self.name = name; self.index = 0; self.kind = "input"
        def __repr__(self): return f"<Dev {self.name}>"
    class FakeList:
        def __init__(self, d): self.inputs = [FakeDevice(n) for n in d["inputs"]]; self.outputs = [FakeDevice(n) for n in d["outputs"]]
    fake_devs_mod = type("M", (), {})()
    fake_devs_mod.list_devices = lambda: FakeList(devices)
    fake_devs_mod.pick_default = lambda lst, kind, all_devices=None: lst[0] if lst else None
    fake_audio_mod = type("M", (), {"devices": fake_devs_mod})()
    monkeypatch.setitem(__import__("sys").modules, "pendantd", type("M", (), {})())
    monkeypatch.setitem(__import__("sys").modules, "pendantd.audio", fake_audio_mod)
    monkeypatch.setitem(__import__("sys").modules, "pendantd.audio.devices", fake_devs_mod)


def test_voice_setup_skips_when_pendantd_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setitem(__import__("sys").modules, "pendantd.audio.devices", None)
    cfg_path = tmp_path / ".robot-md" / "voice.yaml"
    rc = run_voice_setup(robot_name="bob", cfg_path=cfg_path, non_interactive=True)
    assert rc == 0
    assert "pendantd not detected" in capsys.readouterr().out
    assert not cfg_path.exists()


def test_voice_setup_writes_yaml_in_non_interactive(monkeypatch, tmp_path):
    _stub_pendantd(monkeypatch, devices={"inputs": ["USB PnP Sound Device"], "outputs": ["Jabra SPEAK 410"]})
    cfg_path = tmp_path / ".robot-md" / "voice.yaml"
    rc = run_voice_setup(robot_name="bob", cfg_path=cfg_path, non_interactive=True)
    assert rc == 0
    data = yaml.safe_load(cfg_path.read_text())
    assert data["robot_name"] == "bob"
    assert data["wake_word"] == "claude"
    assert data["input_device"] == "USB PnP Sound Device"
    assert data["output_device"] == "Jabra SPEAK 410"


def test_voice_setup_emits_todo_when_no_devices(monkeypatch, tmp_path):
    _stub_pendantd(monkeypatch, devices={"inputs": [], "outputs": []})
    cfg_path = tmp_path / ".robot-md" / "voice.yaml"
    rc = run_voice_setup(robot_name="bob", cfg_path=cfg_path, non_interactive=True)
    assert rc == 0
    text = cfg_path.read_text()
    assert "TODO(voice): no audio devices detected at init time" in text


def test_voice_setup_interactive_accepts_default(monkeypatch, tmp_path):
    _stub_pendantd(monkeypatch, devices={"inputs": ["USB PnP"], "outputs": ["Jabra"]})
    monkeypatch.setattr("sys.stdin", io.StringIO("\n\nn\nn\n"))  # accept defaults; skip tests
    cfg_path = tmp_path / ".robot-md" / "voice.yaml"
    rc = run_voice_setup(robot_name="bob", cfg_path=cfg_path, non_interactive=False, _skip_wake_check=True)
    assert rc == 0
    assert yaml.safe_load(cfg_path.read_text())["input_device"] == "USB PnP"
