"""Replay capture cancellation regressions against immutable dev7 and current code.

Actual gate/RAW C code with SDK fixtures and ASan/UBSan, not camera timing proof.
Expected baseline assertion failures must match the specific regression markers.
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

BASELINE = "build/candidates/MIRROR-0.3.0-dev7-OFFICIAL-LV-CANDIDATE-r2.zip"
BASELINE_SHA = "bec4a21d2439d7b8f341582bf657763928b541d1cd854417835e93b05672348a"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = (args.output or ROOT / "build/capture-cancellation" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    if not output.is_relative_to(ROOT / "build/capture-cancellation"):
        raise ValueError("Cancellation evidence must stay under build/capture-cancellation")
    output.mkdir(parents=True, exist_ok=False)
    archive = ROOT / BASELINE
    if sha(archive.read_bytes()) != BASELINE_SHA:
        raise ValueError("Immutable dev7 baseline changed")
    old = output / "baseline"
    with zipfile.ZipFile(archive) as z:
        for line in z.read("SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            member_name(name)
            if sha(z.read(name)) != digest:
                raise ValueError("Baseline member changed: " + name)
        for name in z.namelist():
            if not name.startswith("source/") or Path(name).suffix not in (".c", ".h", ".inc"):
                continue
            relative = member_name(name.removeprefix("source/"))
            target = old / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
    working = output / "working"
    manifest = json.loads((ROOT / "build/modules/mirror/build.json").read_text())
    for name, digest in manifest["source_files"].items():
        data = (ROOT / name).read_bytes()
        if sha(data) != digest:
            raise ValueError("Working source no longer matches module: " + name)
        target = working / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    fixtures = output / "fixtures"
    fixtures.mkdir()
    fixture_names = ("camera_portability.c", "capture_delivery.c", "preview_sdk.c")
    for path in (ROOT / "tests").iterdir():
        if path.suffix == ".h" or path.name in fixture_names:
            shutil.copyfile(path, fixtures / path.name)
    shutil.copyfile(Path(__file__), output / Path(__file__).name)
    shutil.copyfile(ROOT / "tools/linux_runtime.py", output / "linux_runtime.py")
    shutil.copyfile(ROOT / "build/modules/mirror/build.json", output / "module-build.json")
    runtime = LinuxRuntime(ROOT, "wsl")
    report = {"kind": "capture-cancellation-before-after", "hardware_test": False, "baseline_zip_sha256": BASELINE_SHA,
        "module_sha256": sha((ROOT / "build/modules/mirror/mirror.mo").read_bytes()), "runs": [],
        "evidence_limit": "Host execution of actual gate/renderer/RAW code with a simulated SDK and sanitizer instrumentation. Does not establish physical-camera scheduling, buffer ownership or capture timing."}
    shared = ["modules/mirror/mirror_camera.c", "modules/mirror/mirror_capture_gate.c", "modules/mirror/mirror_raw_trace.c",
        "modules/fx_common/fx_mirror_raw.c", "modules/fx_common/fx_mirror_sensor.c", "modules/fx_common/fx_mirror_registered.c"]
    for label, source in (("dev7", old), ("working", working)):
        relative = source.relative_to(ROOT).as_posix()
        fixture = fixtures.relative_to(ROOT).as_posix()
        flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-DFX_PREFIX=mirror", "-DMIRROR_RELEASE",
            "-DMIRROR_CAMERA_HOST_TEST", "-DFX_GATE_HOST_TEST", "-DFX_TRACE_HOST_TEST",
            "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-no-pie", "-I" + fixture]
        flags += ["-I" + relative + "/" + name for name in ("modules/mirror", "modules/fx_common", "modules/glock", "core")]
        guard = output.relative_to(ROOT).as_posix() + "/" + label + "-guards"
        runtime.run("gcc", *flags, "-DMIRROR_70D_RESEARCH", fixture + "/camera_portability.c",
            *(relative + "/" + name for name in shared), "-o", guard)
        delivery = output.relative_to(ROOT).as_posix() + "/" + label + "-delivery"
        extras = ["modules/fx_common/fx_camera.c", "modules/mirror/mirror_driver.c", "modules/fx_common/fx_mirror.c",
            "modules/fx_common/fx_pixels.c", "modules/glock/gl_review.c", "modules/glock/gl_format.c"]
        runtime.run("gcc", *flags, "-DFX_HOST_TEST", "-DFX_REGISTERED_TEST_HOOK", "-include", relative + "/modules/fx_common/fx_namespace.h",
            fixture + "/capture_delivery.c", fixture + "/preview_sdk.c", *(relative + "/" + name for name in shared + extras), "-o", delivery)
        commands = [("off-on", [guard, "70d-guards"]), ("preflight-and-write", [delivery])]
        if label == "working":
            commands.append(("held-shutdown", [delivery, "held-shutdown"]))
        for name, command in commands:
            result = subprocess.run(runtime.prefix() + command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
            (output / (label + "-" + name + ".log")).write_text(result.stdout, encoding="utf-8")
            if label == "dev7":
                marker = "Capture refusal scenario 15: phase=4 error=0 expected=10 started=1 done=1" if name == "off-on" else "r.phase==MG_FAILED&&r.error==MG_CANCEL&&!r.patch_started&&!r.patch_done"
                valid = result.returncode in (134, -6) and marker in result.stdout and "Assertion" in result.stdout
            else:
                marker = "16 layout/context/latch/overlap/cancel/shutdown/workspace/re-enable rejections: PASS" if name == "off-on" else "RAW cancellation boundary: pre-write source unchanged; post-write complete frame and retained workspace: PASS"
                valid = result.returncode == 0 and marker in result.stdout
            if not valid:
                raise RuntimeError("Unexpected regression outcome: " + label + " / " + name + "\n" + result.stdout)
            report["runs"].append({"source": label, "case": name, "exit_code": result.returncode,
                "expected_baseline_failure": label == "dev7", "matched_marker": marker})
            print(label, name, "expected assertion" if label == "dev7" else "PASS", flush=True)
    report["artifact_files"] = {p.relative_to(output).as_posix(): sha(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Evidence:", output / "results.json")


if __name__ == "__main__":
    main()
