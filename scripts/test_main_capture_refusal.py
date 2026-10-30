"""Verify a stopped 70D research main-module refusal and unchanged Canon CR2.

Synthetic preview/sensor input and a software full-press latch are explicit.
This negative fixture cannot establish successful mirroring or hardware support.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def state(path):
    lines = re.findall(r"^MFLOW_STATE=(.+)$", path.read_text(encoding="utf-8"), re.M)
    if len(lines) != 1:
        raise ValueError("Expected one structured native-flow observation")
    return json.loads(lines[0])


def check_expired_latch(gate):
    if gate["phase"] != 5 or gate["error"] != 7 or gate["latched"] != 1 or gate["installed"] != 1:
        raise ValueError("Main capture gate did not refuse an installed, latched request")
    if any(gate[k] for k in ("patch_started", "patch_done", "patch_verified", "patch_mismatches", "patch_changed", "held_us")):
        raise ValueError("Expired latch reached pixel processing or a scheduling hold")
    # This run's clocks do not wrap. The gate's MG_NO_SHUTTER plus latched=1
    # establishes expiration; the paired timestamps quantify the observed wait.
    latency = gate["enter_us"] / 1000 - gate["full_ms"]
    if not 5000 < latency < 60000:
        raise ValueError("Unexpected expired-latch timestamp relation")
    return latency


def verify(run, module_build):
    import numpy as np
    import rawpy
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_70d_raw_probe import sensor_oracle

    run, module_build = Path(run).resolve(), Path(module_build).resolve()
    if not run.is_relative_to(ROOT) or not module_build.is_relative_to(ROOT / "build/research"):
        raise ValueError("Research inputs must stay in this workspace")
    manifest = json.loads((module_build / "build.json").read_text(encoding="utf-8"))
    if not manifest["research_70d"] or manifest["target"]["camera"] != "70D":
        raise ValueError("Expected an isolated 70D main module")
    module = (run / "mirror.mo").read_bytes()
    module_hash = hashlib.sha256(module).hexdigest()
    if module_hash != manifest["files"]["mirror.mo"] or module != (module_build / "mirror.mo").read_bytes():
        raise ValueError("Observed main module differs from the research build")
    before = state(run / "frame-delivered-check.log")
    armed = state(run / "capture-armed-check.log")
    after = state(run / "capture-complete-state.log")
    cleanup = state(run / "cleanup-state.log")
    if not (before["preview"]["delivery_valid"] == 1 and before["flow"]["completed"] == 2 and before["flow"]["result"] == 1
            and armed["gate"]["phase"] == 2 and armed["gate"]["installed"] == 1 and armed["trace"]["installed"] == 31
            and after["flow"]["completed"] == 4 and after["flow"]["result"] == 0
            and cleanup["flow"]["completed"] == 5 and cleanup["flow"]["result"] == 1
            and cleanup["preview"]["running"] == cleanup["preview"]["allocated"] == cleanup["job"] == 0):
        raise ValueError("Missing delivered-frame, armed-gate, Canon release or cleanup evidence")
    latency = check_expired_latch(after["gate"])
    log = (run / "qemu.log").read_text(encoding="utf-8", errors="replace")
    if re.search(r"ASSERT\s*:|MEMTX invalid", log):
        raise ValueError("Research run contains an assert or unmapped access")
    files = list(run.glob("*.CR2"))
    if len(files) != 1 or files[0].name + " write done" not in log:
        raise ValueError("Expected one completed Canon-written CR2")
    with rawpy.imread(str(files[0])) as raw:
        decoded = raw.raw_image.copy()
    if not np.array_equal(decoded, sensor_oracle(np)):
        raise ValueError("Refused capture did not preserve the independent sensor oracle")
    serial = (run / "serial.log").read_text(encoding="utf-8", errors="replace")
    return {"kind": "research-main-module-expired-latch-refusal", "model": "70D", "firmware": "1.1.2",
            "module_sha256": module_hash, "module_version": manifest["version"],
            "synthetic_preview_injected": True, "software_full_press_injected": True, "patched_emulator": True,
            "main_raw_stage_hook_observed": True, "expired_latch_refused": True,
            "observed_latch_to_stage_ms": latency, "gate": after["gate"], "off_cleanup_verified": True,
            "unchanged_raw_pixels_checked": int(decoded.size), "decoded_raw_shape": list(decoded.shape),
            "cr2_bytes": files[0].stat().st_size, "cr2_sha256": hashlib.sha256(files[0].read_bytes()).hexdigest(),
            "engine_wait_errors": [line for line in serial.splitlines() if "[ENGP] ERROR [FB]" in line or "[ENGP] ERROR [FC]" in line],
            "main_saved_mirrored_cr2_verified": False, "real_liveview_delivery_verified": False, "hardware_test": False,
            "evidence_limit": "Negative main-module capture fixture only. Patched emulator, synthetic preview/sensor input and software full-press. A refused stale latch and original CR2 do not validate successful native mirroring or physical-camera timing."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--module-build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.run, args.module_build)
    with args.output.open("x", encoding="utf-8") as file:
        file.write(json.dumps(report, indent=2) + "\n")
    print("Main RAW-stage expired latch refused;", report["unchanged_raw_pixels_checked"], "original Canon CR2 pixels unchanged")


if __name__ == "__main__":
    main()
