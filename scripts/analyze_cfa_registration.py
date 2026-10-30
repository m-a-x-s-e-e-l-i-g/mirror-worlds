"""Measure RAW optical registration independently of Bayer-cell transport.

Runs immutable 0.2.0 source and current source on a synthetic affine CFA ramp.
This is an algorithm diagnostic, not confirmation of the reported camera defect.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.linux_runtime import LinuxRuntime
from tools.reproducible_zip import member_name
from scripts.verify_release import EXPECTED_ZIP


def digest(data):
    return hashlib.sha256(data).hexdigest()


def diagnostic(text):
    cases = [json.loads(line.split("=", 1)[1]) for line in text.splitlines() if line.startswith("CFA_CASE=")]
    totals = [json.loads(line.split("=", 1)[1]) for line in text.splitlines() if line.startswith("CFA_TOTAL=")]
    if len(cases) != 44 or len(totals) != 1 or totals[0]["cases"] != 44:
        raise ValueError("Incomplete CFA diagnostic")
    if len({(c["mask"], c["dx"], c["dy"]) for c in cases}) != 44:
        raise ValueError("Duplicate CFA cases")
    for key in ("transport_mismatches", "registration_mismatches", "reference_mismatches", "reference_samples", "interior_registration_mismatches", "boundary_extension_samples"):
        if totals[0][key] != sum(c[key] for c in cases):
            raise ValueError("CFA totals disagree with case evidence")
    if totals[0]["transport_mismatches"] or totals[0]["reference_mismatches"]:
        raise ValueError("Packing/transport or the independent reference failed")
    return {"cases": cases, "totals": totals[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--arm", action="store_true", help="Also execute the actual ARM packed kernels on both emulator CPU models")
    parser.add_argument("--registered", action="store_true", help="Also test the working resampler independently of capture")
    parser.add_argument("--expect-registered", action="store_true", help="Fail after recording evidence if current source still has ramp registration errors")
    parser.add_argument("--distro", default="Ubuntu")
    args = parser.parse_args()
    output = (args.output or ROOT / "build/cfa-registration" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    if not output.is_relative_to(ROOT / "build/cfa-registration"):
        raise ValueError("CFA diagnostics must stay under build/cfa-registration")
    output.mkdir(parents=True, exist_ok=False)
    archive = ROOT / "downloads/MIRROR-0.2.0-EOSM202.zip"
    if digest(archive.read_bytes()) != EXPECTED_ZIP:
        raise ValueError("Released source ZIP changed")
    release = output / "release-source"
    with zipfile.ZipFile(archive) as z:
        manifest = json.loads(z.read("BUILD.json"))
        for name, expected in manifest["source_files"].items():
            member_name(name)
            data = z.read("source/" + name)
            if digest(data) != expected:
                raise ValueError("Released source member changed: " + name)
            target = release / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    working = output / "working-source"
    for folder in ("modules/fx_common", "modules/glock", "core"):
        for path in (ROOT / folder).rglob("*"):
            if path.suffix not in (".c", ".h", ".inc") or "build" in path.relative_to(ROOT / folder).parts:
                continue
            target = working / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    shutil.copyfile(ROOT / "tests/cfa_registration.c", output / "diagnostic.c")
    shutil.copyfile(Path(__file__), output / "analyze_cfa_registration.py")
    runtime = LinuxRuntime(ROOT, "wsl", distro=args.distro)
    relative = output.relative_to(ROOT).as_posix()
    report = {"kind": "raw-cfa-optical-registration-diagnostic", "release_zip_sha256": EXPECTED_ZIP,
              "hardware_test": False, "actual_camera_report_fixed": False, "runs": [],
              "evidence_limit": "Synthetic affine-ramp source-kernel execution. Interior registration and outer phase-grid extension are recorded separately. Does not exercise the capture gate or establish the cause or correction of the JPEG camera report."}
    variants = [("release-0.2.0", release), ("working", working)]
    if args.registered:
        variants.append(("working-registered", working))
    for name, source in variants:
        linux_source = runtime.linux_root + "/" + source.relative_to(ROOT).as_posix()
        flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-DFX_PREFIX=cfa", "-DFX_SENSOR_AXIAL_ONLY"]
        flags += ["-I" + linux_source + "/" + directory for directory in ("modules/fx_common", "modules/glock", "core")]
        sources = [relative + "/diagnostic.c", linux_source + "/modules/fx_common/fx_mirror_raw.c", linux_source + "/modules/fx_common/fx_mirror_sensor.c"]
        if name == "working-registered":
            flags.append("-DCFA_REGISTERED")
            sources.append(linux_source + "/modules/fx_common/fx_mirror_registered.c")
        host = relative + "/" + name + "-host"
        runtime.run("gcc", *flags, "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-no-pie", *sources, "-o", host)
        commands = [("host-sanitizers", [host])]
        if args.arm:
            elf = relative + "/" + name + "-arm.elf"
            runtime.run("arm-none-eabi-gcc", *flags, "-march=armv5te", "-marm", "--specs=rdimon.specs", "-Ttext=0x10000", *sources, "-o", elf)
            for cpu in ("arm946-eos", "arm946-eos5"):
                commands.append((cpu, ["env", "QEMU_AUDIO_DRV=none", "timeout", "60", "build/qemu-eos/qemu-system-arm", "-M", "versatilepb", "-cpu", cpu,
                    "-m", "128", "-display", "none", "-monitor", "none", "-serial", "none", "-semihosting-config", "enable=on,target=native", "-kernel", elf, "-no-reboot"]))
        for platform, command in commands:
            text = runtime.output(*command)
            (output / (name + "-" + platform + ".log")).write_text(text, encoding="utf-8")
            result = diagnostic(text)
            report["runs"].append({"source": name, "platform": platform, **result})
            print(name, platform, result["totals"])
    report["artifact_files"] = {p.relative_to(output).as_posix(): digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Diagnostic:", output / "results.json")
    expected_source = "working-registered" if args.registered else "working"
    if args.expect_registered and any(r["source"] == expected_source and r["totals"]["interior_registration_mismatches"] for r in report["runs"]):
        raise SystemExit("Current kernel fails the independent optical-registration criterion; evidence recorded")


if __name__ == "__main__":
    main()
