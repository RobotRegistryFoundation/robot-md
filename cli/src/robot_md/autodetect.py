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
    # Intel RealSense family (common wrist/world cam).
    # Provenance: Intel RealSense docs + librealsense2 udev rules.
    ("8086", "0b07"): {
        "driver_id": "cam-realsense-d435",
        "protocol": "librealsense",
        "role": "camera",
        "label": "Intel RealSense D435",
    },
    ("8086", "0b3a"): {
        "driver_id": "cam-realsense-d435i",
        "protocol": "librealsense",
        "role": "camera",
        "label": "Intel RealSense D435i",
    },
    ("8086", "0b5c"): {
        "driver_id": "cam-realsense-d455",
        "protocol": "librealsense",
        "role": "camera",
        "label": "Intel RealSense D455",
    },
    ("8086", "0b64"): {
        "driver_id": "cam-realsense-l515",
        "protocol": "librealsense",
        "role": "camera",
        "label": "Intel RealSense L515 (LiDAR camera)",
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
    # Arduino family — frequently wired as a motor-driver / sensor-interface
    # co-processor. Provenance: official Arduino USB VID:PID list.
    ("2341", "0043"): {
        "driver_id": "mcu-arduino-uno",
        "protocol": "serial",
        "role": "mcu",
        "label": "Arduino Uno R3 (ATmega328P)",
    },
    ("2341", "0001"): {
        "driver_id": "mcu-arduino-uno-r1",
        "protocol": "serial",
        "role": "mcu",
        "label": "Arduino Uno (original FTDI)",
    },
    ("2341", "0042"): {
        "driver_id": "mcu-arduino-mega2560",
        "protocol": "serial",
        "role": "mcu",
        "label": "Arduino Mega 2560 R3",
    },
    ("2341", "8036"): {
        "driver_id": "mcu-arduino-leonardo",
        "protocol": "serial",
        "role": "mcu",
        "label": "Arduino Leonardo (native USB)",
    },
    # Raspberry Pi RP2040 / Pico. Provenance: rpi-pico docs.
    ("2e8a", "000a"): {
        "driver_id": "mcu-rp2040",
        "protocol": "serial",
        "role": "mcu",
        "label": "Raspberry Pi RP2040 (Pico)",
    },
    ("2e8a", "0003"): {
        "driver_id": "mcu-rp2040-boot",
        "protocol": "serial",
        "role": "mcu",
        "label": "Raspberry Pi RP2040 (BOOTSEL)",
    },
    # Teensy 4.x family — common for high-rate servo/ESC control.
    # Provenance: PJRC usb_desc.h.
    ("16c0", "0483"): {
        "driver_id": "mcu-teensy",
        "protocol": "serial",
        "role": "mcu",
        "label": "PJRC Teensy (HID serial)",
    },
    # ODrive V3.x BLDC motor controller. Provenance: ODrive docs.
    ("1209", "0d32"): {
        "driver_id": "motor-odrive-v3",
        "protocol": "odrive",
        "role": "motor-controller",
        "label": "ODrive V3 BLDC controller",
    },
    # Stereolabs ZED / ZED 2 camera. Provenance: ZED SDK udev rules.
    ("2b03", "f580"): {
        "driver_id": "cam-zed2",
        "protocol": "zed-sdk",
        "role": "camera",
        "label": "Stereolabs ZED 2 stereo camera",
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
class DetectedCameraStream:
    name: str
    intrinsic: dict | None
    baseline_m: float | None
    derived_from: list[str] | None
    width: int
    height: int


@dataclass
class DetectedCamera:
    driver_id: str
    protocol: str
    model: str
    streams: list[DetectedCameraStream]
    provenance: str


@dataclass
class Scan:
    devices: list[Device] = field(default_factory=list)
    runtime: Runtime | None = None
    warnings: list[str] = field(default_factory=list)
    cameras: list[DetectedCamera] = field(default_factory=list)


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


def _probe_servo_buses(devices: list[Device]) -> list[Device]:
    """Actively probe serial ports to discover their actual protocol.

    For each `/dev/ttyACM*` or `/dev/ttyUSB*` in `devices`, call
    `bus_scan.scan_feetech`. If one or more servos respond, emit a
    synthetic `Device(protocol="feetech")` so preset matching can score
    so-arm101 (and its feetech siblings) above alphabetical fallbacks.

    Probes are bounded to ACM/USB tty paths — never `/dev/ttyS*` (built-in
    UARTs often host console/login gettys, and sending Feetech bytes to a
    login shell would be a mess). Opt out via env `ROBOT_MD_SKIP_BUS_PROBE=1`.

    Silent no-op on: missing SDK, no servos, probe exception. Never raises.
    """
    if os.environ.get("ROBOT_MD_SKIP_BUS_PROBE") == "1":
        return []

    out: list[Device] = []
    for d in devices:
        if d.bus != "tty" or not d.path:
            continue
        if not (d.path.startswith("/dev/ttyACM") or d.path.startswith("/dev/ttyUSB")):
            continue
        try:
            from robot_md.bus_scan import scan_feetech  # lazy

            servos = scan_feetech(d.path)
        except Exception:
            continue
        if not servos:
            continue
        leaf = d.path.rsplit("/", 1)[-1]
        out.append(
            Device(
                role="servo-bus",
                driver_id=f"feetech-bus-{leaf}",
                protocol="feetech",
                label=f"Feetech bus on {d.path} ({len(servos)} servos)",
                bus="probe",
                path=d.path,
            )
        )
    return out


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
    # Active bus probe — if a serial tty responds to Feetech protocol, add
    # a synthetic Device(protocol="feetech") so preset matching can score
    # so-arm101 / so-arm101-leader above the alphabetical-first fallback.
    scan.devices.extend(_probe_servo_buses(scan.devices))
    # Compose typed probes (depthai → realsense → v4l2)
    cameras: list[DetectedCamera] = []
    cameras.extend(probe_depthai_cameras())
    cameras.extend(probe_realsense_cameras())
    # v4l2 last — avoid double-listing an OAK-D / RealSense that v4l2 also enumerates
    seen_ids = {c.driver_id for c in cameras}
    for cam in probe_v4l2_cameras():
        if cam.driver_id in seen_ids:
            continue
        cameras.append(cam)
    scan.cameras = cameras
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


# Driver-type profile table — per-protocol defaults autodetect can pre-fill
# into the manifest. Each entry is a best-effort baseline; operators override
# per-deployment. Tier A per spec/autodetect-prefill-roadmap.md.
#
# `steps_per_rev`: encoder resolution per 360° at the servo output shaft —
#   feeds physics.solver.encoder.steps_per_rev.
# `default_baud`: bus baud rate — feeds drivers[].baud_rate when the
#   detected device exposes a serial port.
# `protocol_version`: sub-protocol selector (Feetech=0 SCServo, Dynamixel=2).
DRIVER_PROFILES: dict[str, dict] = {
    "feetech": {"steps_per_rev": 4096, "default_baud": 1_000_000, "protocol_version": 0},
    "scservo": {"steps_per_rev": 4096, "default_baud": 1_000_000, "protocol_version": 0},
    "dynamixel": {"steps_per_rev": 4096, "default_baud": 57_600, "protocol_version": 2},
    "odrive": {"steps_per_rev": 8192, "default_baud": 115_200, "protocol_version": 0},
    # Buses / transports with no single "canonical" baud/encoder:
    "ros2": {},
    "can": {},
    "i2c": {},
    # Cameras / compute — no servo semantics, but known for symmetry:
    "depthai": {},
    "picamera2": {},
    "hailo-rt": {},
    "openvino": {},
}


def driver_profile(protocol: str) -> dict:
    """Return the profile for `protocol`, empty dict if unknown."""
    return DRIVER_PROFILES.get(protocol, {})


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
        # Apply driver profile: prefill baud if known and a port is present.
        prof = driver_profile(d.protocol)
        if prof.get("default_baud") and d.path:
            entry.setdefault("baud_rate", prof["default_baud"])
        out.append(entry)
    return out


def probe_depthai_cameras(
    *, default_width: int = 1280, default_height: int = 720
) -> list[DetectedCamera]:
    """Probe for depthai devices and read factory calibration for each socket.

    Returns [] if depthai is not importable or no device is connected.
    Never raises on import or device failures — this is best-effort.
    """
    try:
        import depthai as dai
    except Exception:
        return []
    try:
        with dai.Device() as device:
            features = device.getConnectedCameraFeatures()
            calib = device.readCalibration()
            model = device.getDeviceName() if hasattr(device, "getDeviceName") else "OAK"
            streams: list[DetectedCameraStream] = []
            for feat in features:
                name = _depthai_socket_to_stream_name(feat)
                if name is None:
                    continue
                intrinsic: dict | None
                try:
                    matrix = calib.getCameraIntrinsics(feat.socket, default_width, default_height)
                    coeffs = list(calib.getDistortionCoefficients(feat.socket))[:5]
                    fx, fy = matrix[0][0], matrix[1][1]
                    cx, cy = matrix[0][2], matrix[1][2]
                    intrinsic = {
                        "fx": float(fx),
                        "fy": float(fy),
                        "cx": float(cx),
                        "cy": float(cy),
                        "width": default_width,
                        "height": default_height,
                        "distortion_model": "plumb_bob",
                        "distortion_coeffs": [float(c) for c in coeffs],
                    }
                except Exception:
                    intrinsic = None
                streams.append(
                    DetectedCameraStream(
                        name=name,
                        intrinsic=intrinsic,
                        baseline_m=None,
                        derived_from=None,
                        width=default_width,
                        height=default_height,
                    )
                )
            if not streams:
                return []
            return [
                DetectedCamera(
                    driver_id=_slugify(model) + "-1",
                    protocol="depthai",
                    model=model,
                    streams=streams,
                    provenance="depthai factory cal",
                )
            ]
    except Exception:
        return []


def _depthai_socket_to_stream_name(feat) -> str | None:
    """Map a depthai CameraFeatures socket to our canonical stream name."""
    name = getattr(feat, "name", None) or ""
    name = str(name).lower()
    if "rgb" in name or "color" in name:
        return "rgb"
    if "left" in name:
        return "left"
    if "right" in name:
        return "right"
    if "mono" in name:
        return "mono"
    return None


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "cam").lower()).strip("-") or "cam"


def probe_v4l2_cameras() -> list[DetectedCamera]:
    """v4l2 enumeration — no factory cal. Emits null intrinsic + provenance."""
    devices = _v4l2_list_devices()
    cams: list[DetectedCamera] = []
    for path in devices:
        caps = _v4l2_device_capabilities(path)
        model = caps.get("model", "USB Camera")
        cams.append(
            DetectedCamera(
                driver_id=_slugify(model) + "-" + Path(path).name,
                protocol="v4l2",
                model=model,
                streams=[
                    DetectedCameraStream(
                        name="rgb",
                        intrinsic=None,
                        baseline_m=None,
                        derived_from=None,
                        width=caps.get("width", 640),
                        height=caps.get("height", 480),
                    )
                ],
                provenance="v4l2 enum / no cal",
            )
        )
    return cams


def _v4l2_list_devices() -> list[str]:
    return sorted(str(p) for p in Path("/dev").glob("video*") if p.exists())


def _v4l2_device_capabilities(path: str) -> dict:
    """Return {model, width, height} via v4l2-ctl if available; defaults otherwise."""
    if shutil.which("v4l2-ctl") is None:
        return {}
    try:
        info = subprocess.check_output(
            ["v4l2-ctl", "-d", path, "--info"], timeout=2, text=True, stderr=subprocess.DEVNULL
        )
    except Exception:
        return {}
    model = "USB Camera"
    for line in info.splitlines():
        if "Card type" in line:
            model = line.split(":", 1)[1].strip()
            break
    return {"model": model, "width": 640, "height": 480}


def probe_realsense_cameras() -> list[DetectedCamera]:
    """pyrealsense2 probe. Import-guarded stub for now."""
    try:
        import pyrealsense2 as rs  # noqa: F401
    except Exception:
        return []
    # Minimal: do not hit hardware here — expanded implementation is a follow-up.
    return []


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
        "  # TODO: arm | arm_manipulator | wheeled | tracked | legged"
        " | arm+camera | humanoid | other"
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
    if scan.cameras:
        lines.append("cameras:")
        for c in scan.cameras:
            lines.append(
                f"  - {{ id: {c.driver_id!r}, protocol: {c.protocol!r}, model: {c.model!r} }}"
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
