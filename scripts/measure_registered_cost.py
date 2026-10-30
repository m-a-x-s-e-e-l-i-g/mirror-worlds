"""Compare RAW kernel instruction cost with an immutable candidate in QEMU.

Synthetic EOS M-sized buffers, deterministic instruction clock; not hardware time.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.linux_runtime import LinuxRuntime
from tools.reproducible_zip import member_name

BASELINE = "build/candidates/MIRROR-0.3.0-dev8-OFFICIAL-LV-CANDIDATE.zip"
BASELINE_SHA = "e014d31992574db8ca337a0e761e63208c839e9fe979313751105521c3ee83f8"
BASELINES = {
    "dev8": (BASELINE, BASELINE_SHA),
    "dev11": ("build/candidates/MIRROR-0.3.0-dev11-OFFICIAL-LV-CANDIDATE.zip",
              "be48ed001ef2c16da8fe1cc3fadd87562f998268d6cb9f6ccbd9f0751f335625"),
    "dev13": ("build/candidates/MIRROR-0.3.0-dev13-OFFICIAL-LV-CANDIDATE.zip",
              "f0402223272fc7378ca67d9b2ed75a7582148971048d37f011856bf1ede0512f"),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--baseline-version", choices=BASELINES, default="dev8")
    parser.add_argument("--allow-output-change", action="store_true", help="Record different output hashes for a deliberate mapping change; correctness must be checked separately")
    args = parser.parse_args()
    output = (args.output or ROOT / "build/registered-cost" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    if not output.is_relative_to(ROOT / "build/registered-cost"):
        raise ValueError("Cost evidence must stay under build/registered-cost")
    output.mkdir(parents=True, exist_ok=False)
    baseline_name = args.baseline_version
    if args.allow_output_change and baseline_name != "dev13":
        raise ValueError("Output-change comparison is restricted to the dev13 interpolation baseline")
    baseline_path, baseline_sha = BASELINES[baseline_name]
    archive = ROOT / baseline_path
    if sha(archive.read_bytes()) != baseline_sha:
        raise ValueError("Immutable candidate source archive changed")
    baseline = output / baseline_name
    with zipfile.ZipFile(archive) as z:
        for line in z.read("SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            member_name(name)
            if sha(z.read(name)) != digest:
                raise ValueError("Baseline member changed: " + name)
        for name in z.namelist():
            if not name.startswith("source/") or Path(name).suffix not in (".c", ".h", ".inc"):
                continue
            target = baseline / member_name(name.removeprefix("source/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
    variants = [(baseline_name, baseline)]
    if not args.baseline_only:
        working = output / "working"
        for folder in ("modules/fx_common", "modules/glock", "core"):
            for path in (ROOT / folder).rglob("*"):
                if path.suffix not in (".c", ".h", ".inc") or "build" in path.relative_to(ROOT / folder).parts:
                    continue
                target = working / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        variants.append(("working", working))
    shutil.copyfile(ROOT / "tests/registered_cost.c", output / "registered_cost.c")
    shutil.copyfile(Path(__file__), output / Path(__file__).name)
    runtime = LinuxRuntime(ROOT, "wsl")
    base = output.relative_to(ROOT).as_posix()
    report = {"kind": "synthetic-arm-raw-instruction-cost", "baseline_version": baseline_name, "baseline_zip_sha256": baseline_sha, "hardware_test": False,
        "output_change_allowed": args.allow_output_change, "correctness_verified": False,
        "icount_ns_per_instruction": 1, "timer_hz": 1000000, "qemu_sha256": sha((ROOT / "build/qemu-eos/qemu-system-arm").read_bytes()),
        "evidence_limit": "Generic VersatilePB board and EOS M-sized synthetic packed buffers. Deterministic instruction clock, no Canon firmware, cache/bus latency or physical-camera timing proof.", "runs": []}
    for name, source in variants:
        relative = source.relative_to(ROOT).as_posix()
        flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-DFX_PREFIX=cost", "-march=armv5te", "-marm", "--specs=rdimon.specs", "-Ttext=0x10000"]
        flags += ["-I" + relative + "/" + p for p in ("modules/fx_common", "modules/glock", "core")]
        elf = base + "/" + name + ".elf"
        runtime.run("arm-none-eabi-gcc", *flags, base + "/registered_cost.c", relative + "/modules/fx_common/fx_mirror_raw.c",
            relative + "/modules/fx_common/fx_mirror_registered.c", "-o", elf)
        for cpu in ("arm946-eos", "arm946-eos5"):
            command = ["env", "QEMU_AUDIO_DRV=none", "timeout", "180", "build/qemu-eos/qemu-system-arm", "-M", "versatilepb", "-cpu", cpu,
                "-m", "128", "-display", "none", "-monitor", "none", "-serial", "none", "-semihosting-config", "enable=on,target=native",
                "-icount", "shift=0,align=off,sleep=off", "-kernel", elf, "-no-reboot"]
            result = subprocess.run(runtime.prefix() + command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            (output / (name + "-" + cpu + ".log")).write_text(result.stdout, encoding="utf-8")
            (output / (name + "-" + cpu + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
            cases = [json.loads(line.split("=", 1)[1]) for line in result.stdout.splitlines() if line.startswith("RAW_COST=")]
            if len(cases) != 3 or {c["mask"] for c in cases} != {2, 4, 15} or any(c["icount_ticks"] <= 0 for c in cases):
                raise ValueError("Incomplete RAW cost evidence")
            report["runs"].append({"source": name, "cpu": cpu, "cases": cases})
            print(name, cpu, cases, flush=True)
    if not args.baseline_only:
        for cpu in ("arm946-eos", "arm946-eos5"):
            old, new = [next(r for r in report["runs"] if r["source"] == label and r["cpu"] == cpu) for label in (baseline_name, "working")]
            for a, b in zip(old["cases"], new["cases"]):
                if any(a[k] != b[k] for k in ("mask", "dx", "dy")) or not args.allow_output_change and a["checksum"] != b["checksum"]:
                    raise ValueError("Compared RAW outputs differ")
    report["artifact_files"] = {p.relative_to(output).as_posix(): sha(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Evidence:", output / "results.json")


if __name__ == "__main__":
    main()
