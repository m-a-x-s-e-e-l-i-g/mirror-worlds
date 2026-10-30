"""Run actual ARM preview code on the ML emulator's DIGIC 4/5 CPU models.

This is a synthetic CPU/pixel test, not a Canon firmware boot or module-load test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.linux_runtime import LinuxRuntime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=("wsl", "docker"), default="wsl")
    parser.add_argument("--distro", default="Ubuntu")
    args = parser.parse_args()
    runtime = LinuxRuntime(ROOT, args.runtime, "mirror-worlds-qemu-eos:bookworm", args.distro)
    output = ROOT / "build/tests"
    output.mkdir(parents=True, exist_ok=True)
    binary = "build/tests/preview-arm.elf"
    sources = ["tests/preview_portability.c", "tests/preview_sdk.c", "modules/fx_common/fx_camera.c", "modules/mirror/mirror_driver.c",
               "modules/fx_common/fx_mirror.c", "modules/fx_common/fx_pixels.c", "modules/glock/gl_review.c", "modules/glock/gl_format.c"]
    runtime.run("arm-none-eabi-gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-march=armv5te", "-marm",
                "--specs=rdimon.specs", "-Ttext=0x10000", "-DFX_PREFIX=mirror", "-DMIRROR_RELEASE", "-DFX_HOST_TEST",
                "-include", "modules/fx_common/fx_namespace.h", "-Itests", "-Imodules/mirror", "-Imodules/fx_common",
                "-Imodules/glock", "-Icore", *sources, "-o", binary)
    evidence = {"kind": "synthetic-arm-preview", "canon_firmware_booted": False, "module_load_verified": False,
                "native_capture_verified": False, "elf_sha256": hashlib.sha256((ROOT / binary).read_bytes()).hexdigest(), "cpus": []}
    for cpu in ("arm946-eos", "arm946-eos5"):
        command = ["env", "QEMU_AUDIO_DRV=none", "timeout", "120", "build/qemu-eos/qemu-system-arm",
                   "-M", "versatilepb", "-cpu", cpu, "-m", "128", "-display", "none", "-monitor", "none", "-serial", "none",
                   "-semihosting-config", "enable=on,target=native", "-kernel", binary, "-no-reboot"]
        result = runtime.output(*command)
        print(cpu + ": " + result.strip())
        if "44 layouts at 720x480 and 720x240" not in result or ": PASS" not in result:
            raise RuntimeError("Missing preview oracle completion: " + cpu)
        if "9 invalidation/resume cases at both LCD heights: PASS" not in result:
            raise RuntimeError("Missing delivery validity completion: " + cpu)
        evidence["cpus"].append({"cpu": cpu, "layouts_verified": 88, "delivery_cases_verified": 18, "result": "passed"})
    (output / "arm-preview.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
