"""Verify the specific research main-module Right/Half Canon CR2 fixture.

Completion-only patched emulator, synthetic preview/sensor and software shutter.
This verifies main-module integration, not a physical-camera port or timing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def linked_evidence(run, module_build, qemu_build, input_receipt, extra_files):
    """Validate the observed build cohort before hashing its non-ROM evidence."""
    files = {}

    def add(path, expected=None):
        path = path.resolve()
        if not path.is_relative_to(ROOT) or path.suffix.lower() == ".raw" or path.name.upper() in (
                "ROM0.BIN", "ROM1.BIN", "SFDATA.BIN"):
            raise ValueError("Evidence must stay inside the workspace and exclude ROM/card images")
        actual = digest(path)
        if expected is not None and actual != expected:
            raise ValueError("Changed evidence: " + path.relative_to(ROOT).as_posix())
        files[path.relative_to(ROOT).as_posix()] = actual
        return actual

    manifest = json.loads((module_build / "build.json").read_text(encoding="utf-8"))
    add(module_build / "build.json")
    for name, expected in manifest["files"].items():
        add(module_build / name, expected)
    for name, expected in manifest["source_files"].items():
        add(ROOT / name, expected)
    normal_build = ROOT / "build/modules/mirror"
    normal = json.loads((normal_build / "build.json").read_text(encoding="utf-8"))
    if normal["source_files"] != manifest["source_files"] or normal["version"] != manifest["version"] or normal.get("research_70d"):
        raise ValueError("Research result must be linked to the same source as the normal module")
    add(normal_build / "build.json")
    normal_hash = add(normal_build / "mirror.mo", normal["files"]["mirror.mo"])
    source = json.loads((qemu_build / "source.json").read_text(encoding="utf-8"))
    if source["kind"] != "experimental-completion-only-qemu-source" or source["requires_environment"] != "QEMU_EOS_FENCING_RESEARCH=1":
        raise ValueError("Expected the opt-in completion-only emulator")
    add(qemu_build / "source.json")
    qemu_hash = add(qemu_build / "qemu-system-arm", source["qemu_sha256"])
    add(qemu_build / "plugins/libmagiclantern.so")
    add(qemu_build / "source.patch", source["patch_sha256"])
    for name, expected in source["files"].items():
        add(qemu_build / "source" / name, expected)
    session = json.loads((run / "session.json").read_text(encoding="utf-8"))
    if session["research_qemu_sha256"] != qemu_hash or session["module_sha256"] != manifest["files"]["mirror.mo"]:
        raise ValueError("Observed emulator/module differs from its build cohort")
    inputs = json.loads(input_receipt.read_text(encoding="utf-8"))
    if inputs["target"] != "70D.112":
        raise ValueError("Expected the coherent 70D.112 core/card cohort")
    add(input_receipt)
    for kind, name in (("core", "core.elf"), ("autoexec", "autoexec.from-card"), ("symbols", "symbols.from-card")):
        add(run / name, inputs["artifacts"][kind]["sha256"])
    for name in ("mirror", "mflow"):
        if digest(run / (name + ".mo")) != digest(run / (name + ".from-card")):
            raise ValueError("Loaded card module differs from the observed build")
    if digest(run / "mirror.mo") != manifest["files"]["mirror.mo"]:
        raise ValueError("Observed main module differs from the research build")
    required = ["session.json", "core.elf", "autoexec.from-card", "symbols.from-card", "serial.log", "qemu.log",
                "mirror.mo", "mirror.from-card", "mflow.mo", "mflow.from-card", "frame-delivered-check.log",
                "capture-armed-check.log", "capture-complete-state.log", "cleanup-state.log", "shoot.log",
                "jp57-input.u16", "jp57-output.ljpeg", "jp57-layout.json"]
    for name in required:
        add(run / name)
    for path in run.glob("*.CR2"):
        add(path)
    for name in ("scripts/test_main_registered_capture.py", "scripts/test_70d_raw_probe.py",
                 "scripts/test_qemu_cr2.py", "tests/test_main_registered_capture.py",
                 "tools/freeze_research_receipt.py", "tests/fencing_research.c",
                 "targets/70D.112/fencing-research.json", "tests/qemu_native_flow/mflow.c",
                 "tests/qemu_native_flow/Makefile", "tests/qemu_native_flow/README.rst"):
        add(ROOT / name)
    for path in extra_files:
        add(path)
    return files, normal_hash, source["revision"], qemu_hash


def state(path):
    lines = re.findall(r"^MFLOW_STATE=(.+)$", path.read_text(encoding="utf-8"), re.M)
    if len(lines) != 1:
        raise ValueError("Expected exactly one structured main-flow observation")
    return json.loads(lines[0])


def check_completed_gate(after, params=(180, 2, 2, 2)):
    gate = after["gate"]
    if not (gate["phase"] == 4 and gate["error"] == 0 and gate["installed"] == gate["latched"] == 1
            and gate["sample_mode"] == 3 and gate["params"] == list(params)
            and gate["patch_started"] == gate["patch_done"] == 1 and gate["patch_verified"] == 896
            and gate["patch_mismatches"] == gate["overlaps"] == gate["changed"] == 0
            and gate["before_count"] == gate["after_count"] == 896 and gate["patch_changed"] > 0):
        raise ValueError("Expected a completed and verified full-frame main capture with the requested controls")
    latency_us = (gate["enter_us"] - gate["full_ms"] * 1000) & 0xffffffff
    held_us = (gate["release_us"] - gate["enter_us"]) & 0xffffffff
    if not (latency_us < 5001000 and 100000 <= held_us <= 2000000 and held_us == gate["held_us"]
            and 0 < gate["patch_us"] <= held_us):
        raise ValueError("Capture did not meet the unchanged latch/hold timing checks")
    source = gate["source"] & ~0x40000000
    address = gate["dma_address"] & ~0x40000000
    pointer = gate["dma_pointer"] & ~0x40000000
    if not (0x1000 <= source < 0x20000000 and address == source + 9884 and pointer == address + 36768480
            and gate["dma_before"] == gate["dma_after"] == 0 and gate["context"] == 0x7c15c
            and gate["lr"] == 0xff15c4d0 and gate["cpsr"] & 0xff == 0x13):
        raise ValueError("Capture context or completed readout differs from the selected research backend")
    if after["workspace"]["held"] or after["workspace"]["gate_data"]:
        raise ValueError("Capture did not release its private workspace")
    if after["raw_map"] != {"frame": {"format": 1, "height": 3720, "pitch": 9884, "size": 36768480, "width": 5648},
                             "region": [60, 156, 3708, 5628]}:
        raise ValueError("Unexpected RAW geometry or active rectangle")
    return latency_us / 1000


def verify(run, module_build, qemu_build, input_receipt, extra_files=()):
    import numpy as np
    import rawpy
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_70d_raw_probe import sensor_oracle
    from test_qemu_cr2 import tiff_ifds
    run, module_build = Path(run).resolve(), Path(module_build).resolve()
    if not run.is_relative_to(ROOT) or not module_build.is_relative_to(ROOT / "build/research"):
        raise ValueError("Research paths must stay inside the workspace")
    qemu_build = Path(qemu_build).resolve()
    if not qemu_build.is_relative_to(ROOT / "build"):
        raise ValueError("Emulator evidence must stay inside workspace build/")
    evidence, normal_hash, qemu_revision, qemu_hash = linked_evidence(run, module_build, qemu_build, input_receipt, extra_files)
    manifest = json.loads((module_build / "build.json").read_text(encoding="utf-8"))
    module_hash = hashlib.sha256((run / "mirror.mo").read_bytes()).hexdigest()
    if not manifest["research_70d"] or manifest["target"]["camera"] != "70D" or module_hash != manifest["files"]["mirror.mo"]:
        raise ValueError("Expected the exact isolated 70D main module")
    before = state(run / "frame-delivered-check.log")
    armed = state(run / "capture-armed-check.log")
    after = state(run / "capture-complete-state.log")
    cleanup = state(run / "cleanup-state.log")
    if not (before["preview"]["delivery_valid"] == 1 and before["flow"]["completed"] == 2 and before["flow"]["result"] == 1
            and armed["gate"]["phase"] == 2 and armed["gate"]["installed"] == 1 and armed["trace"]["installed"] == 31
            and after["flow"]["completed"] == 4 and after["flow"]["result"] == 0
            and cleanup["flow"]["completed"] == 5 and cleanup["flow"]["result"] == 1
            and cleanup["preview"]["allocated"] == cleanup["preview"]["running"] == cleanup["job"] == 0
            and cleanup["workspace"]["canvas_bytes"] == 0
            and cleanup["workspace"]["held"] == cleanup["workspace"]["gate_data"] == 0):
        raise ValueError("Missing delivered frame, armed gate, Canon Release or cleanup evidence")
    latency = check_completed_gate(after)
    log = (run / "qemu.log").read_text(encoding="utf-8", errors="replace")
    if re.search(r"ASSERT\s*:|MEMTX invalid|DRYOS PANIC|Illegal inter", log):
        raise ValueError("Assert, invalid access or panic in the capture run")
    for marker in ("IRQ D0 after 5 DMA ticks", "IRQ D1 after 314 DMA ticks"):
        if log.count("[FENCE70R] bounded synthetic preprocessing completion " + marker) != 1:
            raise ValueError("Missing or duplicated bounded preprocessing completion")
    files = list(run.glob("*.CR2"))
    if len(files) != 1 or files[0].name + " write done" not in log:
        raise ValueError("Expected one completed Canon-written CR2")
    data = files[0].read_bytes()
    tables = tiff_ifds(data)
    if tables[3][0xc640] != [1, 2784, 2784]:
        raise ValueError("Unexpected Canon RAW slice layout")
    start, size = tables[3][273][0], tables[3][279][0]
    if data[start:start + size] != (run / "jp57-output.ljpeg").read_bytes():
        raise ValueError("Saved Canon RAW strip differs from the encoder output")
    with rawpy.imread(str(files[0])) as raw:
        decoded = raw.raw_image.copy()
    baseline = sensor_oracle(np)
    expected = baseline.copy()
    # Independent geometric pixel reflection and same-phase interpolation.
    # CR2 crop begins at full-sensor x=72,y=10. The active rectangle becomes
    # x=[84,5556),y=[50,3698); Right/Half begins at cropped column 2820.
    x = np.arange(2820, 5556, dtype=np.int32)
    reflected = 5639 - x
    lo = np.maximum(reflected - 1, 84 + (x & 1))
    hi = np.minimum(reflected + 1, 5554 + (x & 1))
    expected[50:3698, 2820:5556] = (baseline[50:3698, lo] + baseline[50:3698, hi] + 1) // 2
    if decoded.shape != expected.shape or not np.array_equal(decoded, expected):
        raise ValueError("Canon CR2 pixels differ from the independent registered mirror reference")
    changed = int(np.count_nonzero(decoded != baseline))
    margin = np.ones(decoded.shape, dtype=bool)
    margin[50:3698, 84:5556] = False
    if changed <= 1000000 or not np.array_equal(decoded[margin], baseline[margin]):
        raise ValueError("Missing full mirror effect or changed optical-black margins")
    return {"kind": "research-main-module-registered-cr2", "model": "70D", "firmware": "1.1.2",
            "module_sha256": module_hash, "normal_module_sha256": normal_hash, "module_version": manifest["version"],
            "qemu_revision": qemu_revision, "qemu_sha256": qemu_hash, "files": evidence, "params": after["gate"]["params"],
            "raw_pixels_checked": int(decoded.size), "changed_pixels": changed, "raw_pixel_mismatches": 0,
            "unchanged_margin_pixels": int(np.count_nonzero(margin)), "gate": after["gate"],
            "observed_latch_to_stage_ms": latency, "off_cleanup_verified": True,
            "cr2_bytes": len(data), "cr2_sha256": hashlib.sha256(data).hexdigest(),
            "main_saved_mirrored_cr2_verified": True, "synthetic_preview_injected": True,
            "synthetic_sensor_input": True, "software_full_press_injected": True, "patched_emulator": True,
            "completion_only_preprocessing_model": True, "real_liveview_delivery_verified": False, "hardware_test": False,
            "native_backend_enabled_in_normal_module": False,
            "evidence_limit": "One Right/Half main-module capture with synthetic inputs in a completion-only patched emulator. Independent LibRaw decoding verifies all saved RAW samples. No physical key path, real Canon LiveView stream, hardware timing or promotion of native 70D support."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--module-build", type=Path, required=True)
    parser.add_argument("--qemu-build", type=Path, required=True)
    parser.add_argument("--input-receipt", type=Path, required=True)
    parser.add_argument("--evidence-file", type=Path, action="append", default=[], help="Additional non-ROM reproduction evidence to freeze")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.run, args.module_build, args.qemu_build, args.input_receipt, args.evidence_file)
    with args.output.open("x", encoding="utf-8") as file:
        file.write(json.dumps(report, indent=2) + "\n")
    print("Main module Canon CR2:", report["raw_pixels_checked"], "registered samples match;", report["changed_pixels"], "changed; margins original")


if __name__ == "__main__":
    main()
