"""Test existing API-8/API-7 .mo files on ARM with a synthetic SDK, without ROMs.

This links the existing module into a semihosting ELF. It tests neither ML's
dynamic loader nor Canon firmware, physical-camera structures or native capture.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_module import inspect_module
from tools.camera_matrix import module_profiles
from tools.linux_runtime import LinuxRuntime


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def check_log(text, major, profiles):
    if "BINARY FIXTURE FAIL" in text:
        raise ValueError("ARM binary fixture failed")
    rows = re.findall(r"^BINARY_PROFILE ([A-Za-z0-9]+) ([0-9.]+) ([78]) (240|480) PASS$", text, re.M)
    expected = {(p["model"], p["firmware"]) for p in profiles}
    actual = {(model, firmware) for model, firmware, _, _ in rows}
    if len(rows) != len(expected) or actual != expected or any(
            int(api) != major or int(height) != (240 if model == "1100D" else 480) for model, _, api, height in rows):
        raise ValueError("Missing, duplicate or incorrect ARM binary profile observations")
    marker = f"BINARY_MODULE_RESULT api={major} profiles={len(expected)} unsupported=1 sensor_reads=0 PASS"
    if text.count(marker) != 1:
        raise ValueError("Missing or duplicate ARM binary completion")
    return [{"model": model, "firmware": firmware, "height": int(height), "passed": True,
             "native_backend_selected": major == 8 and model == "EOSM"}
            for model, firmware, _, height in rows]


def compile_fixture(output, sdk, corrupted=False):
    """Linux compiler entry; the existing .mo is only linked, never recompiled."""
    output, sdk = Path(output).resolve(), Path(sdk).resolve()
    name = "corrupted" if corrupted else "fixture"
    flags = ["-Os", "-g3", "-std=gnu99", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", "-Wno-unused-function",
             "-march=armv5te", "-marm", "-D__ARM__", "-DMODULE", "-DMODULE_NAME=fixture", "-DCONFIG_MAGICLANTERN", "-DFX_PREFIX=mirror"]
    if corrupted:
        flags.append("-DBINARY_CORRUPT_OUTPUT")
    for path in (output, sdk / "src", sdk / "include", sdk / "platform/all", ROOT / "modules/fx_common",
                 ROOT / "modules/mirror", ROOT / "modules/glock", ROOT / "core"):
        flags.append("-I" + str(path))
    subprocess.run(["arm-none-eabi-gcc", *flags, "-MMD", "-MF", str(output / (name + ".d")), "-c",
                    str(ROOT / "tests/arm_module_binary.c"), "-o", str(output / (name + ".o"))], check=True)
    subprocess.run(["arm-none-eabi-gcc", "-march=armv5te", "-marm", "--specs=rdimon.specs", "-Ttext=0x10000",
                    "-Wl,-Map=" + str(output / (name + ".map")), str(output / (name + ".o")),
                    str(output / "mirror.mo"), "-o", str(output / (name + ".elf"))], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api7-build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--distro", default="Ubuntu")
    args = parser.parse_args()
    output, api7 = args.output.resolve(), args.api7_build.resolve()
    if not output.is_relative_to(ROOT / "build/compatibility") or not api7.is_relative_to(ROOT / "build/research"):
        parser.error("Use workspace build/compatibility and isolated API-7 research paths")
    if output.exists():
        raise FileExistsError(output)
    normal = ROOT / "build/modules/mirror"
    manifest = json.loads((normal / "build.json").read_text())
    experiment = json.loads((api7 / "results.json").read_text())
    if manifest.get("research_70d") or not experiment["preview_only"] or experiment["native_capture"]:
        raise ValueError("Expected normal API-8 and preview-only API-7 modules")
    for name, expected in manifest["source_files"].items():
        if digest(ROOT / name) != expected or (api7 / "sources" / name).exists() and digest(api7 / "sources" / name) != expected:
            raise ValueError("Normal/API-7 module sources differ: " + name)
    for name, expected in experiment["artifact_files"].items():
        if digest(api7 / name) != expected:
            raise ValueError("Changed API-7 build evidence: " + name)
    qemu = ROOT / "build/qemu-eos"
    qemu_build = json.loads((qemu / "build.json").read_text())
    if digest(qemu / "qemu-system-arm") != qemu_build["files"]["qemu-system-arm"]:
        raise ValueError("Changed pinned emulator")
    profiles = module_profiles(ROOT / "modules/mirror/mirror_camera.c")
    runtime = LinuxRuntime(ROOT, "wsl", distro=args.distro)
    output.mkdir(parents=True)
    sources = {"scripts/test_arm_module_binary.py", "tests/arm_module_binary.c", "tools/linux_runtime.py",
               "tools/audit_module.py", "tools/camera_matrix.py", "modules/mirror/mirror_camera.c"}
    report = {"kind": "synthetic-arm-module-binaries", "canon_firmware_booted": False, "ml_loader_tested": False,
              "installed_core_layout_verified": False, "native_capture_verified": False, "hardware_tested": False,
              "module_source_recompiled": False, "profiles": profiles, "variants": [],
              "qemu_revision": qemu_build["revision"], "qemu_sha256": qemu_build["files"]["qemu-system-arm"],
              "compiler": runtime.output("arm-none-eabi-gcc", "--version").splitlines()[0],
              "evidence_limit": "Existing .mo files linked into ARM semihosting executables against a synthetic SDK. Actual init/menu/property/preview/preferences/cleanup code runs for each named profile; Canon firmware, ML loader, installed core layouts, real LV, native RAW and hardware are not validated. API-7 deployment export checks remain limited to the pinned 7D archive."}
    for major, build, sdk, expected in ((8, normal, ROOT / ".cache/ml-upstream", manifest["files"]["mirror.mo"]),
                                       (7, api7, api7 / "sdk", experiment["module_sha256"])):
        destination = output / ("api" + str(major))
        (destination / "build").mkdir(parents=True)
        for stub in (destination / "module_strings.h", destination / "build/module_strings.h"):
            stub.write_text("#define MODULE_STRINGS()\n")
        shutil.copyfile(build / "mirror.mo", destination / "mirror.mo")
        if digest(destination / "mirror.mo") != expected:
            raise ValueError("Module input differs from its build")
        inspected = inspect_module((destination / "mirror.mo").read_bytes(), api_major=major)
        variant = {"api_major": major, "module_sha256": expected, "module_path": (destination / "mirror.mo").relative_to(ROOT).as_posix(),
                   "preview_only": major == 7, "imports": len(inspected["imports"]), "cpus": []}
        relative = destination.relative_to(ROOT).as_posix()
        sdk_relative = sdk.relative_to(ROOT).as_posix()
        for corrupted in (False, True) if major == 8 else (False,):
            with (destination / ("corrupt-build.log" if corrupted else "build.log")).open("w") as log:
                runtime.run("python3", "-B", "-c", "from scripts.test_arm_module_binary import compile_fixture;compile_fixture(" +
                            repr(relative) + "," + repr(sdk_relative) + "," + repr(corrupted) + ")", stdout=log, stderr=subprocess.STDOUT)
        for cpu in ("arm946-eos", "arm946-eos5"):
            command = ["env", "QEMU_AUDIO_DRV=none", "timeout", "120", "build/qemu-eos/qemu-system-arm", "-M", "versatilepb",
                       "-cpu", cpu, "-m", "128", "-display", "none", "-monitor", "none", "-serial", "none",
                       "-semihosting-config", "enable=on,target=native", "-kernel", relative + "/fixture.elf", "-no-reboot"]
            with (destination / (cpu + ".log")).open("w") as log:
                runtime.run(*command, stdout=log, stderr=subprocess.STDOUT)
            result = check_log((destination / (cpu + ".log")).read_text(), major, profiles)
            variant["cpus"].append({"cpu": cpu, "profiles": result, "unsupported_firmware_refused": True,
                                     "preview_source_and_destination_checked": True, "off_on_and_cleanup_verified": True,
                                     "initial_review_seed_verified": True, "review_invalidates_delivery": True, "forbidden_sensor_reads": 0})
            print("API", major, cpu + ":", len(result), "actual-module synthetic profiles passed", flush=True)
        if major == 8:
            command[command.index(relative + "/fixture.elf")] = relative + "/corrupted.elf"
            with (destination / "corruption-rejected.log").open("w") as log:
                negative = subprocess.run(runtime.prefix() + command, stdout=log, stderr=subprocess.STDOUT)
            text = (destination / "corruption-rejected.log").read_text()
            if negative.returncode != 1 or "BINARY FIXTURE FAIL" not in text or "BINARY_MODULE_RESULT" in text:
                raise ValueError("Deliberate preview corruption was not rejected")
            report["deliberate_corruption_rejected"] = True
        for path in destination.glob("*.d"):
            dependencies = path.read_text().replace("\\\n", " ").split(":", 1)[1].split()
            for name in dependencies:
                if name.startswith(runtime.linux_root + "/"):
                    name = name[len(runtime.linux_root) + 1:]
                path = (ROOT / name).resolve()
                if not path.is_relative_to(ROOT):
                    raise ValueError("Unexpected compiler dependency outside workspace")
                if not path.is_relative_to(output):
                    sources.add(path.relative_to(ROOT).as_posix())
        report["variants"].append(variant)
    for name in sources:
        target = output / "sources" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    for path, name in ((normal / "build.json", "api8-module-build.json"), (api7 / "results.json", "api7-build-results.json"),
                       (api7 / "sdk-receipt.json", "api7-sdk-receipt.json"), (qemu / "build.json", "qemu-build.json")):
        shutil.copyfile(path, output / name)
    report["artifact_files"] = {p.relative_to(ROOT).as_posix(): digest(p) for p in output.rglob("*") if p.is_file()}
    report["profile_runs_verified"] = sum(len(cpu["profiles"]) for variant in report["variants"] for cpu in variant["cpus"])
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Actual .mo ARM fixture:", report["profile_runs_verified"], "profile runs; simulated SDK only;", output / "results.json")


if __name__ == "__main__":
    main()
