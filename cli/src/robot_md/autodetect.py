"""Hardware + runtime autodiscovery for `robot-md autodetect`.

Linux-only (Pi, generic x86). Scope for v0.1.2:

- PCI enumeration (via `lspci -nn` if available)
- USB enumeration (via `lsusb` if available)
- /dev/ttyACM* and /dev/ttyUSB* character devices
- Runtime: Python, OS release, presence of known robot-stack commands

Out of scope this pass:
- I2C (sudo-gated, produces false negatives without it)
- macOS / Windows
- GPU-vendor query beyond PCI ID match
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Hardware DB — VID:PID → meaning                                             #
# --------------------------------------------------------------------------- #
# Each entry is tagged with provenance: where the VID:PID was observed, so
# future PRs don't regress devices that already work.
# Keep this DB small and high-confidence. False positives are worse than
# gaps — an operator can add missing devices, but a wrong call erodes trust.

# format: (vendor_id_hex, device_id_hex) → {driver_id, protocol, role, label}
PCI_DB: dict[tuple[str, str], dict[str, str]] = {
    # Hailo-8 AI Processor. Provenance: Pi 5 + Hailo-8 kit (/dev/hailo0).
    ("1e60", "2864"): {
        "driver_id": "npu-hailo8",
        "protocol": "hailo-rt",
        "role": "npu",
        "label": "Hailo-8 AI Processor",
        "dev_node": "/dev/hailo0",
    },
    # Hailo-10H. Provenance: Hailo docs (not on this box; future-proof).
    ("1e60", "2865"): {
        "driver_id": "npu-hailo10",
        "protocol": "hailo-rt",
        "role": "npu",
        "label": "Hailo-10H AI Processor",
        "dev_node": "/dev/hailo0",
    },
}

USB_DB: dict[tuple[str, str], dict[str, str]] = {
    # Intel Movidius Neural Compute Stick 2 (MA2485). Provenance: this box.
    ("03e7", "f63b"): {
        "driver_id": "npu-movidius-ncs2",
        "protocol": "openvino",
        "role": "npu",
        "label": "Intel Myriad VPU (Movidius NCS 2)",
    },
    # Movidius NCS 1 (legacy, MA2450). Provenance: Intel docs.
    ("03e7", "2150"): {
        "driver_id": "npu-movidius-ncs1",
        "protocol": "openvino",
        "role": "npu",
        "label": "Intel Myriad VPU (Movidius NCS 1)",
    },
    # QinHeng CH340 USB-Serial. Commonly used by SO-ARM101-class servo buses.
    # Provenance: this box (Bus 003 Device 002), SO-ARM101 kit docs.
    ("1a86", "55d3"): {
        "driver_id": "serial-ch340",
        "protocol": "serial",
        "role": "serial-bus",
        "label": "QinHeng CH340 USB-Serial (servo-bus candidate)",
    },
    # CH341 sibling, same risk profile. Provenance: ubiquitous.
    ("1a86", "7523"): {
        "driver_id": "serial-ch341",
        "protocol": "serial",
        "role": "serial-bus",
        "label": "QinHeng CH341 USB-Serial",
    },
    # Silicon Labs CP210x (common USB-TTL). Provenance: ubiquitous, SiLabs docs.
    ("10c4", "ea60"): {
        "driver_id": "serial-cp210x",
        "protocol": "serial",
        "role": "serial-bus",
        "label": "Silicon Labs CP210x USB-UART",
    },
    # FTDI FT232R. Provenance: FTDI docs.
    ("0403", "6001"): {
        "driver_id": "serial-ft232r",
        "protocol": "serial",
        "role": "serial-bus",
        "label": "FTDI FT232R USB-UART",
    },
    # Luxonis OAK-D (Movidius-based). Provenance: Luxonis docs.
    ("03e7", "2485"): {
        "driver_id": "cam-oak-d",
        "protocol": "depthai",
        "role": "camera",
        "label": "Luxonis OAK-D camera",
    },
    ("03e7", "f63c"): {
        "driver_id": "cam-oak-d-bootloader",
        "protocol": "depthai",
        "role": "camera",
        "label": "Luxonis OAK-D (bootloader)",
    },
    # Intel RealSense D435/D455 family (common wrist/world cam).
    # Provenance: Intel RealSense docs.
    ("8086", "0b07"): {
        "driver_id": "cam-realsense-d435",
        "protocol": "librealsense",
        "role": "camera",
        "label": "Intel RealSense D435",
    },
    # Google Coral USB Accelerator (EdgeTPU). Provenance: Coral docs.
    ("1a6e", "089a"): {
        "driver_id": "npu-coral-usb",
        "protocol": "edgetpu",
        "role": "npu",
        "label": "Google Coral USB Accelerator",
    },
    ("18d1", "9302"): {
        "driver_id": "npu-coral-usb-bootloader",
        "protocol": "edgetpu",
        "role": "npu",
        "label": "Google Coral USB (bootloader)",
    },
}


# --------------------------------------------------------------------------- #
# Data types                                                                  #
# --------------------------------------------------------------------------- #


@dataclass
class Device:
    role: str
    driver_id: str
    protocol: str
    label: str
    vid: str | None = None
    pid: str | None = None
    bus: str | None = None  # "pci" | "usb"
    path: str | None = None  # /dev/hailo0, /dev/ttyACM0, ...
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class Runtime:
    python: str
    platform: str
    os_release: str | None
    tools_found: dict[str, str | None] = field(default_factory=dict)


@dataclass
class Scan:
    devices: list[Device] = field(default_factory=list)
    runtime: Runtime | None = None
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# PCI                                                                         #
# --------------------------------------------------------------------------- #

# e.g. "0001:01:00.0 Co-processor [0b40]: Hailo Ltd. Hailo-8 AI Processor [1e60:2864] (rev 01)"
_PCI_LINE = re.compile(
    r"^(?P<slot>\S+)\s+"
    r"(?P<class_name>[^[]+)\[(?P<class_id>[0-9a-f]{4})\]:\s+"
    r"(?P<vendor_device>.+?)\s+"
    r"\[(?P<vid>[0-9a-f]{4}):(?P<pid>[0-9a-f]{4})\]"
    r"(?:\s+\(rev\s+[0-9a-f]+\))?\s*$",
    re.IGNORECASE,
)


def parse_pci(lspci_output: str) -> list[Device]:
    devs: list[Device] = []
    for line in lspci_output.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _PCI_LINE.match(line)
        if not m:
            continue
        vid, pid = m.group("vid").lower(), m.group("pid").lower()
        hit = PCI_DB.get((vid, pid))
        if not hit:
            continue
        devs.append(
            Device(
                role=hit["role"],
                driver_id=hit["driver_id"],
                protocol=hit["protocol"],
                label=hit["label"],
                vid=vid,
                pid=pid,
                bus="pci",
                path=hit.get("dev_node"),
                extra={"pci_slot": m.group("slot")},
            )
        )
    return devs


# --------------------------------------------------------------------------- #
# USB                                                                         #
# --------------------------------------------------------------------------- #

# e.g. "Bus 002 Device 004: ID 03e7:f63b Intel Myriad VPU [Movidius Neural Compute Stick]"
_USB_LINE = re.compile(
    r"^Bus\s+(?P<bus>\d+)\s+Device\s+(?P<dev>\d+):\s+"
    r"ID\s+(?P<vid>[0-9a-f]{4}):(?P<pid>[0-9a-f]{4})"
    r"(?:\s+(?P<label>.+))?$",
    re.IGNORECASE,
)


def parse_usb(lsusb_output: str) -> list[Device]:
    devs: list[Device] = []
    for line in lsusb_output.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _USB_LINE.match(line)
        if not m:
            continue
        vid, pid = m.group("vid").lower(), m.group("pid").lower()
        hit = USB_DB.get((vid, pid))
        if not hit:
            continue
        devs.append(
            Device(
                role=hit["role"],
                driver_id=hit["driver_id"],
                protocol=hit["protocol"],
                label=hit["label"],
                vid=vid,
                pid=pid,
                bus="usb",
                extra={
                    "usb_bus": m.group("bus"),
                    "usb_dev": m.group("dev"),
                },
            )
        )
    return devs


# --------------------------------------------------------------------------- #
# Serial (tty)                                                                #
# --------------------------------------------------------------------------- #


def scan_tty(dev_dir: Path = Path("/dev")) -> list[Device]:
    devs: list[Device] = []
    if not dev_dir.exists():
        return devs
    for name in sorted(os.listdir(dev_dir)):
        if not (name.startswith("ttyACM") or name.startswith("ttyUSB")):
            continue
        devs.append(
            Device(
                role="serial-port",
                driver_id=f"tty-{name}",
                protocol="serial",
                label=f"serial port /dev/{name}",
                path=str(dev_dir / name),
                bus="tty",
            )
        )
    return devs


# --------------------------------------------------------------------------- #
# Runtime                                                                     #
# --------------------------------------------------------------------------- #

_TOOLS_TO_PROBE = ("claude", "opencastor", "castor", "rcan-validate", "hailortcli", "i2cdetect")


def detect_runtime() -> Runtime:
    os_release: str | None = None
    rel_path = Path("/etc/os-release")
    if rel_path.exists():
        # Parse KEY=VALUE pairs; prefer PRETTY_NAME.
        for raw in rel_path.read_text().splitlines():
            if raw.startswith("PRETTY_NAME="):
                os_release = raw.split("=", 1)[1].strip().strip('"')
                break
    tools: dict[str, str | None] = {}
    for tool in _TOOLS_TO_PROBE:
        found = shutil.which(tool)
        tools[tool] = found
    return Runtime(
        python=sys.version.split()[0],
        platform=platform.platform(),
        os_release=os_release,
        tools_found=tools,
    )


# --------------------------------------------------------------------------- #
# Orchestration                                                               #
# --------------------------------------------------------------------------- #


def _run(cmd: list[str]) -> str | None:
    """Run cmd, return stdout on success, None on missing binary or error."""
    if not shutil.which(cmd[0]):
        return None
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def scan_system() -> Scan:
    """Run the full scan against the live system. Linux-only."""
    scan = Scan()
    if sys.platform != "linux":
        scan.warnings.append(
            f"autodetect is Linux-only in v0.1.2 (running on {sys.platform}). "
            "Emitting runtime info only."
        )
        scan.runtime = detect_runtime()
        return scan

    lspci_out = _run(["lspci", "-nn"])
    if lspci_out is None:
        scan.warnings.append("lspci unavailable — skipping PCI scan")
    else:
        scan.devices.extend(parse_pci(lspci_out))

    lsusb_out = _run(["lsusb"])
    if lsusb_out is None:
        scan.warnings.append("lsusb unavailable — skipping USB scan")
    else:
        scan.devices.extend(parse_usb(lsusb_out))

    scan.devices.extend(scan_tty())
    scan.runtime = detect_runtime()
    return scan


# --------------------------------------------------------------------------- #
# Emit draft ROBOT.md                                                         #
# --------------------------------------------------------------------------- #

_DRAFT_HEADER_YAML_COMMENT = (
    "# TODO: review this draft before committing.\n"
    "# `robot-md autodetect` fills physics/drivers from visible hardware; you must\n"
    "# fill in identity, capabilities, safety limits, and any non-USB/PCI peripherals.\n"
    "# Run `robot-md validate ROBOT.md` after editing.\n"
)


def _dof_guess(devices: list[Device]) -> int:
    """Guess DoF from serial buses present. Conservative: unknown → 0."""
    # Presence of a serial-bus (CH340/CP210x/FTDI) strongly suggests a
    # servo chain, but we cannot know how many servos without probing. 0
    # forces the operator to fill it in; that is the right default.
    return 0


def _physics_type(devices: list[Device]) -> str:
    # Without asking hardware questions we cannot know arm vs wheeled. Play
    # safe: "other" with a TODO. Cameras alone might suggest a sensor node,
    # but emitting the wrong type is worse than emitting "other".
    return "other"


def _drivers_from_devices(devices: list[Device]) -> list[dict]:
    out: list[dict] = []
    seen_ids: set[str] = set()
    for d in devices:
        if d.driver_id in seen_ids:
            continue
        seen_ids.add(d.driver_id)
        entry: dict = {"id": d.driver_id, "protocol": d.protocol}
        if d.path:
            entry["port"] = d.path
        if d.vid and d.pid:
            entry["usb_id" if d.bus == "usb" else "pci_id"] = f"{d.vid}:{d.pid}"
        out.append(entry)
    return out


def _capabilities_from_devices(devices: list[Device]) -> list[str]:
    caps: list[str] = []
    has_camera = any(d.role == "camera" for d in devices)
    has_npu = any(d.role == "npu" for d in devices)
    if has_camera:
        caps.append("vision.describe")
    if has_npu:
        caps.append("vision.infer")
    return caps


def emit_draft(scan: Scan) -> str:
    """Produce a draft ROBOT.md string that validates against the v1 schema
    but is clearly marked for operator review (TODOs in required identity
    fields)."""
    drivers = _drivers_from_devices(scan.devices)
    caps = _capabilities_from_devices(scan.devices)
    dof = _dof_guess(scan.devices)
    ptype = _physics_type(scan.devices)

    lines: list[str] = []
    lines.append("---")
    lines.append(_DRAFT_HEADER_YAML_COMMENT.rstrip())
    lines.append('rcan_version: "3.0"')
    lines.append("metadata:")
    lines.append('  robot_name: "CHANGE-ME"  # TODO: short display name; must match H1 below')
    lines.append('  rrn: ""  # blank until `robot-md register` (v0.2) returns one')
    lines.append("physics:")
    lines.append(
        f'  type: "{ptype}"'
        "  # TODO: arm | wheeled | tracked | legged | arm+camera | humanoid | other"
    )
    lines.append(f"  dof: {dof}  # TODO: actuator count (0 is valid for sensor-only nodes)")
    if drivers:
        lines.append("drivers:")
        for d in drivers:
            flat = ", ".join(
                f"{k}: {v!r}" if isinstance(v, str) else f"{k}: {v}" for k, v in d.items()
            )
            lines.append(f"  - {{ {flat} }}")
    else:
        lines.append("drivers:")
        lines.append(
            "  - { id: change-me, protocol: change-me }  # TODO: no drivers detected; add yours"
        )
    if caps:
        lines.append("capabilities:")
        for c in caps:
            lines.append(f"  - {c}")
    else:
        lines.append("capabilities: []  # TODO: fill in capabilities this robot exposes")
    lines.append("safety:")
    lines.append("  estop:")
    lines.append("    software: true")
    lines.append("    response_ms: 200  # TODO: review; schema cap is 5000")
    lines.append("---")
    lines.append("")
    lines.append("# CHANGE-ME")  # matches metadata.robot_name
    lines.append("")
    lines.append("## Identity")
    lines.append("")
    lines.append("TODO: 1-2 sentences. What this robot is, in plain English.")
    lines.append("")
    lines.append("## What CHANGE-ME Can Do")
    lines.append("")
    lines.append("TODO: describe each capability in plain English.")
    lines.append("")
    lines.append("## Safety Gates")
    lines.append("")
    lines.append("TODO: describe the E-stop, HITL requirements, and any scope limits.")
    lines.append("")
    if scan.devices or scan.runtime:
        lines.append("## Detected environment")
        lines.append("")
        lines.append("<!-- Generated by `robot-md autodetect`. Safe to remove after review. -->")
        lines.append("")
        if scan.devices:
            for d in scan.devices:
                ids = []
                if d.vid and d.pid:
                    ids.append(f"{d.bus}:{d.vid}:{d.pid}")
                if d.path:
                    ids.append(d.path)
                suffix = f" ({', '.join(ids)})" if ids else ""
                lines.append(f"- **{d.role}** — {d.label}{suffix}")
        if scan.runtime:
            r = scan.runtime
            lines.append(f"- **runtime** — Python {r.python} on {r.platform}")
            if r.os_release:
                lines.append(f"- **os** — {r.os_release}")
            found = [k for k, v in r.tools_found.items() if v]
            if found:
                lines.append(f"- **tools available** — {', '.join(found)}")
        lines.append("")
    if scan.warnings:
        lines.append("## Autodetect warnings")
        lines.append("")
        for w in scan.warnings:
            lines.append(f"- {w}")
        lines.append("")
    return "\n".join(lines)
