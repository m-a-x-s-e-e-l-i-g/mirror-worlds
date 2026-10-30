"""Validate exact-sample RAW reflection against an out-of-place reference.

Host sanitizers and optional actual ARM execution; no Canon ownership claim.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.linux_runtime import LinuxRuntime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = (args.output or ROOT / "build/registered-raw" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    if not output.is_relative_to(ROOT / "build/registered-raw"):
        raise ValueError("Output must stay under build/registered-raw")
    output.mkdir(parents=True, exist_ok=False)
    sources = ["tests/registered_raw.c", "modules/fx_common/fx_mirror_registered.c", "modules/fx_common/fx_mirror_raw.c"]
    for folder in ("modules/fx_common", "modules/glock", "core"):
        for path in (ROOT / folder).rglob("*"):
            if path.suffix not in (".c", ".h", ".inc") or "build" in path.relative_to(ROOT / folder).parts:
                continue
            target = output / "source" / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    (output / "source/tests").mkdir()
    shutil.copyfile(ROOT / sources[0], output / "source" / sources[0])
    shutil.copyfile(Path(__file__), output / Path(__file__).name)
    runtime = LinuxRuntime(ROOT, "wsl")
    base = output.relative_to(ROOT).as_posix()
    flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-DFX_PREFIX=registered", "-DFX_REGISTERED_TEST_HOOK"]
    flags += ["-I" + base + "/source/" + p for p in ("modules/fx_common", "modules/glock", "core")]
    source_args = [base + "/source/" + s for s in sources]
    host = base + "/registered-host"
    runtime.run("gcc", *flags, "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-no-pie", *source_args, "-o", host)
    commands = [("host-sanitizers", [host])]
    if args.arm:
        elf = base + "/registered-arm.elf"
        runtime.run("arm-none-eabi-gcc", *flags, "-march=armv5te", "-marm", "--specs=rdimon.specs", "-Ttext=0x10000", *source_args, "-o", elf)
        for cpu in ("arm946-eos", "arm946-eos5"):
            commands.append((cpu, ["env", "QEMU_AUDIO_DRV=none", "timeout", "120", "build/qemu-eos/qemu-system-arm", "-M", "versatilepb", "-cpu", cpu,
                "-m", "128", "-display", "none", "-monitor", "none", "-serial", "none", "-semihosting-config", "enable=on,target=native", "-kernel", elf, "-no-reboot"]))
    report = {"kind": "bounded-registered-raw-reference", "hardware_test": False, "capture_integration_exercised": False, "runs": []}
    for name, command in commands:
        text = runtime.output(*command)
        (output / (name + ".log")).write_text(text, encoding="utf-8")
        results = [json.loads(line.split("=", 1)[1]) for line in text.splitlines() if line.startswith("REGISTERED_RAW=")]
        if len(results) != 1 or results[0]["cases"] != 3432 or results[0]["mismatches"] or not results[0]["optical_samples"] or not results[0].get("exact_source_samples") or "post-write completion PASS" not in text:
            raise RuntimeError("Incomplete registered RAW evidence: " + name)
        print(name, results[0])
        report["runs"].append({"platform": name, **results[0]})
    report["artifact_files"] = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob("*")) if p.is_file()}
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Evidence:", output / "results.json")


if __name__ == "__main__":
    main()
