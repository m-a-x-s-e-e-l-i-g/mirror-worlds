"""Independently verify Canon CR2 pixels and lifecycle from the native regression runner."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.test_main_registered_capture import check_completed_gate, state, digest
from tools.run_native_capture import request_finished


def coordinates(np, extent, divisor, low, high):
    """Reflect individual pixel centers and interpolate only matching CFA parity."""
    pixel = np.arange(extent, dtype=np.int32)
    border = 2 * ((extent // 2) // divisor)
    reflected = np.where((pixel < border) & bool(low), 2 * border - 1 - pixel,
                        np.where((pixel >= extent - border) & bool(high), 2 * (extent - border) - 1 - pixel, pixel))
    folds = reflected != pixel
    first = np.where(folds, np.maximum(reflected - 1, pixel & 1), pixel)
    second = np.where(folds, np.minimum(reflected + 1, extent - 2 + (pixel & 1)), pixel)
    return first, second


def expected_pixels(np, baseline, params):
    tag, edges, dx, dy = params
    if tag != 180 or edges not in (1, 2, 4, 8, 3, 12, 15) or not 2 <= dx <= 6 or not 2 <= dy <= 6 or (edges & 3 == 3 and dx == 2) or (edges & 12 == 12 and dy == 2):
        raise ValueError("Invalid edge mirror parameters")
    result = baseline.copy()
    x0, x1 = coordinates(np, 5472, dx, edges & 1, edges & 2)
    y0, y1 = coordinates(np, 3648, dy, edges & 4, edges & 8)
    x0, x1, y0, y1 = x0 + 84, x1 + 84, y0 + 50, y1 + 50
    for row in range(0, 3648, 128):
        end = min(row + 128, 3648)
        a = (baseline[y0[row:end, None], x0[None, :]] + baseline[y1[row:end, None], x0[None, :]] + 1) // 2
        b = (baseline[y0[row:end, None], x1[None, :]] + baseline[y1[row:end, None], x1[None, :]] + 1) // 2
        result[50 + row:50 + end, 84:5556] = (a + b + 1) // 2
    return result


def verify(run):
    import numpy as np
    import rawpy
    sys.path.insert(0, str(ROOT / "scripts"))
    from test_70d_raw_probe import sensor_oracle
    from test_qemu_cr2 import tiff_ifds
    run = run.resolve()
    if not run.is_relative_to(ROOT / "build/research"):
        raise ValueError("Research run must stay under build/research")
    record = json.loads((run / "run.json").read_text(encoding="utf-8"))
    if not (record["kind"] == "research-main-module-native-sequence" and record["observations_passed"] and
            record["shutdown"] == "qmp_quit" and record["exit_code"] == 0 and record["cr2_extracted_after_shutdown"] and
            record["synthetic_preview_injected"] and record["synthetic_sensor_input"] and record["software_full_press_injected"] and
            record["patched_emulator"] and record["software_liveview_start_injected"] and
            not record["hardware_test"] and not record["raw_pixels_verified"]):
        raise ValueError("Missing isolated emulator lifecycle evidence or incompatible support claims")
    params = [[180, 2, 2, 2], [180, 15, 3, 3], [180, 4, 2, 2]]
    if [shot["params"] for shot in record["shots"]] != params or not all(shot["job"] for shot in record["shots"]) or len({shot["cr2"] for shot in record["shots"]}) != 3:
        raise ValueError("Expected three capture jobs/photos and the requested settings")
    cancel = state(run / record["cancel_state"])
    if not (request_finished(cancel, 7, cancel["flow"]["ticket"]) and cancel["flow"]["result"] == 1 and
            cancel["gate"]["latched"] == 1 and cancel["gate"]["phase"] == 5 and cancel["gate"]["error"] == 10 and
            cancel["gate"]["patch_started"] == cancel["gate"]["patch_done"] == 0 and
            cancel["workspace"]["held"] == cancel["workspace"]["gate_data"] == 0):
        raise ValueError("Cancellation was not verified before sensor processing")
    cleanup = state(run / record["cleanup_state"])
    if not (cleanup["preview"]["allocated"] == cleanup["preview"]["running"] == cleanup["job"] ==
            cleanup["workspace"]["held"] == cleanup["workspace"]["gate_data"] == cleanup["workspace"]["canvas_bytes"] == 0):
        raise ValueError("Native sequence did not clean up after OFF")
    log = (run / "qemu.log").read_text(encoding="utf-8", errors="replace")
    if re.search(r"ASSERT\s*:|MEMTX invalid|DRYOS PANIC|Illegal inter", log):
        raise ValueError("Canon assert, invalid access or panic in native regression")
    for irq, ticks in (("D0", 5), ("D1", 314)):
        if log.count(f"[FENCE70R] bounded synthetic preprocessing completion IRQ {irq} after {ticks} DMA ticks") != 3:
            raise ValueError("Missing or duplicated synthetic preprocessing completion")
    files = {}

    def add(path, expected=None):
        path = path.resolve()
        if not path.is_relative_to(ROOT) or path.suffix.lower() == ".raw" or path.name.upper() in ("ROM0.BIN", "ROM1.BIN", "SFDATA.BIN"):
            raise ValueError("Invalid non-ROM evidence path")
        actual = digest(path)
        if expected is not None and actual != expected:
            raise ValueError("Changed native regression evidence: " + str(path))
        files[path.relative_to(ROOT).as_posix()] = actual
        return actual

    mirror, helper, qemu = (ROOT / record[key] for key in ("mirror_build", "helper_build", "qemu_build"))
    for build in (mirror, helper):
        manifest = json.loads((build / "build.json").read_text())
        add(build / "build.json")
        for name, expected in manifest["files"].items():
            add(build / name, expected)
    manifest = json.loads((mirror / "build.json").read_text())
    for name, expected in manifest["source_files"].items():
        add(ROOT / name, expected)
    for name in ("mirror", "mflow"):
        build = mirror if name == "mirror" else helper
        if digest(run / (name + ".mo")) != digest(build / (name + ".mo")) or digest(run / (name + ".from-card")) != digest(build / (name + ".mo")):
            raise ValueError("Observed card module differs from its build")
    source = json.loads((qemu / "source.json").read_text())
    add(qemu / "source.json")
    add(qemu / "qemu-system-arm", source["qemu_sha256"])
    add(qemu / "source.patch", source["patch_sha256"])
    add(qemu / "plugins/libmagiclantern.so")
    for name, expected in source["files"].items():
        add(qemu / "source" / name, expected)
    bundle = json.loads((ROOT / record["input_receipt"]).read_text())
    add(ROOT / record["input_receipt"])
    for name, expected in record.get("runner_source_files", {}).items():
        add(run / name, expected)
    for kind, name in (("core", "core.elf"), ("autoexec", "autoexec.from-card"), ("symbols", "symbols.from-card")):
        add(run / name, bundle["artifacts"][kind]["sha256"])
    normal_build = ROOT / "build/modules/mirror"
    normal = json.loads((normal_build / "build.json").read_text())
    if normal["source_files"] != manifest["source_files"] or normal.get("research_70d"):
        raise ValueError("Normal and research main modules do not have the same source")
    add(normal_build / "build.json")
    normal_hash = add(normal_build / "mirror.mo", normal["files"]["mirror.mo"])
    baseline = sensor_oracle(np)
    margin = np.ones(baseline.shape, dtype=bool)
    margin[50:3698, 84:5556] = False
    shots, latch_times, release_tickets = [], set(), set()
    for shot in record["shots"]:
        directory = run / shot["directory"]
        before, armed, after = [state(directory / name) for name in (
            "frame-delivered-check.log", "capture-armed-check.log", "capture-complete-state.log")]
        if not (before["preview"]["delivery_valid"] and armed["gate"]["phase"] == 2 and
                request_finished(after, 4, after["flow"]["ticket"]) and after["flow"]["result"] == 0):
            raise ValueError("Missing fresh preview, arm or ticketed Canon release")
        latency = check_completed_gate(after, shot["params"])
        if after["gate"]["job"] != shot["job"] or after["gate"]["source"] != shot["source"]:
            raise ValueError("Capture job/source differs from the recorded shot")
        latch_times.add(after["gate"]["full_ms"])
        release_tickets.add(after["flow"]["completed_ticket"])
        data = (directory / shot["cr2"]).read_bytes()
        if log.count(shot["cr2"] + " write done") != 1:
            raise ValueError("Canon did not complete exactly one write for this photo")
        tables = tiff_ifds(data)
        start, size = tables[3][273][0], tables[3][279][0]
        if tables[3][0xc640] != [1, 2784, 2784] or data[start:start + size] != (directory / "jp57-output.ljpeg").read_bytes():
            raise ValueError("Canon RAW strip differs from the observed encoder output")
        with rawpy.imread(str(directory / shot["cr2"])) as raw:
            decoded = raw.raw_image.copy()
        expected = expected_pixels(np, baseline, shot["params"])
        if decoded.shape != expected.shape or not np.array_equal(decoded, expected) or not np.array_equal(decoded[margin], baseline[margin]):
            raise ValueError("Saved RAW or margins differ from independent registered reflection: " + shot["directory"])
        changed = int(np.count_nonzero(decoded != baseline))
        if changed <= 1000000:
            raise ValueError("Missing full mirror effect")
        shots.append({**shot, "raw_pixels_checked": int(decoded.size), "raw_pixel_mismatches": 0,
                      "changed_pixels": changed, "unchanged_margin_pixels": int(np.count_nonzero(margin)),
                      "latch_to_stage_ms": latency, "cr2_sha256": hashlib.sha256(data).hexdigest()})
    if len(latch_times) != 3 or len(release_tickets) != 3:
        raise ValueError("Repeated captures reused an earlier shutter latch or command completion")
    for path in run.rglob("*"):
        if path.is_file() and "evidence" not in path.relative_to(run).parts and not path.name.endswith("receipt.json"):
            add(path)
    for name in ("tools/run_native_capture.py", "tools/qemu_native_flow.gdb.py", "tools/build_native_flow_control.py",
                 "tools/run_camera_matrix_linux.py", "tools/linux_runtime.py", "scripts/test_main_registered_capture.py",
                 "tools/extract_native_capture.py",
                 "scripts/test_native_capture_sequence.py", "scripts/test_70d_raw_probe.py", "scripts/test_qemu_cr2.py",
                 "tests/test_native_capture_sequence.py", "tools/freeze_research_receipt.py"):
        add(ROOT / name)
    for name in ("tools/camera_matrix.py", "tests/test_camera_matrix.py", "targets/70D.112/README.md",
                 "targets/70D.112/emulator-research.md", "docs/emulation.md"):
        add(ROOT / name)
    return {"kind": "research-main-module-native-sequence-verified", "model": "70D", "firmware": "1.1.2",
            "module_sha256": manifest["files"]["mirror.mo"], "normal_module_sha256": normal_hash,
            "shots": shots, "raw_pixels_checked": sum(shot["raw_pixels_checked"] for shot in shots),
            "raw_pixel_mismatches": 0, "cancellation_before_mutation_verified": True,
            "consecutive_shots_in_one_boot_verified": True, "off_cleanup_verified": True, "qmp_shutdown_verified": True,
            "synthetic_preview_injected": True, "software_full_press_injected": True, "synthetic_sensor_input": True,
            "software_liveview_start_injected": True,
            "completion_only_preprocessing_model": True, "real_liveview_delivery_verified": False,
            "hardware_test": False, "native_backend_enabled_in_normal_module": False, "files": files,
            "evidence_limit": "Three main-module Canon-saved CR2s and pre-capture cancellation recovery in one emulator boot. Synthetic preview/sensor, software latch/Release and LV_START property, completion-only patched preprocessing. No physical keys, real Canon LV delivery or hardware timing proof; normal 70D native support stays disabled."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.run)
    with args.output.open("x", encoding="utf-8") as file:
        file.write(json.dumps(result, indent=2) + "\n")
    print("Native sequence:", result["raw_pixels_checked"], "saved RAW pixels match; cancellation and OFF cleanup verified")


if __name__ == "__main__":
    main()
