"""Record observed Canon/ML startup and module init, without inferring preview or RAW tests."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def analyze(serial, gdb_state, firmware, canon_id):
    states = [json.loads(line.removeprefix("MIRROR_QEMU_STATE=")) for line in gdb_state.splitlines()
              if line.startswith("MIRROR_QEMU_STATE=")]
    if len(states) != 1:
        raise ValueError("Exactly one structured GDB state observation is required")
    state = states[0]
    version = re.search(r"\b" + re.escape(canon_id) + r" ICU Firmware Version " + re.escape(firmware) + r"\s*\(", serial)
    canon_started = bool(version) and "startupInitializeComplete" in serial
    ml_started = canon_started and state["ml_started"] == 1
    matches = [m for m in state["modules"] if m["name"] == "mirror"]
    loaded = ml_started and len(matches) == 1 and all((matches[0].get("info_name") == "mirror",
        matches[0].get("api") == [90, 8, 0, 0], matches[0]["status"] == "OK",
        matches[0]["valid"] == 1, matches[0]["enabled"] == 1, matches[0]["error"] == 0))
    # ML startup precedes the asynchronous module loader. Absence or an
    # intermediate status is not evidence of a failed init. Only an explicit
    # loader error can terminate the runner before successful initialization.
    failed = ml_started and any(m.get("error", 0) != 0 for m in matches)
    return {"canon_startup_observed": canon_started, "ml_startup_observed": ml_started,
            "module_initialization_observed": loaded, "observed_module_state": matches,
            "module_initialization_failed_observed": failed,
            "module_initialization_state": "initialized" if loaded else "failed" if failed else "pending",
            "liveview_flag_at_observation": state["lv"], "preview_render_verified": False,
            "native_raw_capture_verified": False, "hardware_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--firmware", required=True)
    parser.add_argument("--canon-id", required=True)
    parser.add_argument("--serial", type=Path, required=True)
    parser.add_argument("--gdb-state", type=Path, required=True)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--autoexec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"kind": "observed-qemu-module-initialization", "model": args.model, "firmware": args.firmware,
              "canon_id": args.canon_id, **analyze(args.serial.read_text(errors="replace"), args.gdb_state.read_text(), args.firmware, args.canon_id)}
    report["artifacts"] = {name: {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                           for name, path in (("serial", args.serial), ("gdb_state", args.gdb_state), ("module", args.module),
                                              ("core", args.core), ("autoexec", args.autoexec))}
    report["evidence_limit"] = "Observed emulator state with a caller-supplied matching core ELF and firmware identity. It does not attest input origin, sensor operation, rendering, capture timing or physical-camera behavior."
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("model", "firmware", "canon_startup_observed", "ml_startup_observed", "module_initialization_observed", "preview_render_verified", "native_raw_capture_verified")}))


if __name__ == "__main__":
    main()
