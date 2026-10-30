"""Exercise actual module code on the host CPU using the existing builder image."""
from pathlib import Path
import argparse
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "glitchlock-ml-builder:bookworm"
sys.path.insert(0, str(ROOT))
from tools.linux_runtime import LinuxRuntime

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true", help="Enable address and undefined-behavior sanitizers")
    parser.add_argument("--runtime", choices=("docker", "wsl"), default="docker")
    parser.add_argument("--distro", default="Ubuntu")
    args = parser.parse_args()
    run = LinuxRuntime(ROOT, args.runtime, IMAGE, args.distro).run
    (ROOT / "build/tests").mkdir(parents=True, exist_ok=True)
    flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-DFX_PREFIX=mirror", "-DMIRROR_RELEASE",
             "-Itests", "-Imodules/mirror", "-Imodules/fx_common", "-Imodules/glock", "-Icore"]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer", "-no-pie", "-g"]
    run("gcc", *flags, "tests/display_memory.c", "-o", "build/tests/display-memory")
    run("build/tests/display-memory")
    run("gcc", *flags, "-DFX_REGISTERED_TEST_HOOK", "tests/registered_raw.c", "modules/fx_common/fx_mirror_raw.c",
        "modules/fx_common/fx_mirror_registered.c", "-o", "build/tests/registered-raw")
    run("build/tests/registered-raw")
    run("gcc", *flags, "-DMIRROR_PREVIEW_ONLY", "-DMIRROR_CAMERA_HOST_TEST",
        "tests/preview_only.c", "modules/mirror/mirror_camera.c", "modules/mirror/mirror_native_disabled.c",
        "-o", "build/tests/preview-only")
    run("build/tests/preview-only")
    run("gcc", *flags, "-Wno-unused-function", "-Wno-unused-parameter",
        "-include", "modules/fx_common/fx_namespace.h", "-DMIRROR_PREVIEW_ONLY", "-DFX_MIRROR_UI_HOST_TEST",
        "-DFX_SETTINGS_HOST_TEST", "-DFX_HOST_TEST", "-DMIRROR_CAMERA_HOST_TEST",
        "tests/module_lifecycle.c", "tests/preview_sdk.c", "modules/mirror/mirror_settings.c",
        "modules/mirror/mirror_camera.c", "modules/mirror/mirror_native_disabled.c", "modules/fx_common/fx_camera.c",
        "modules/mirror/mirror_driver.c", "modules/fx_common/fx_mirror.c", "modules/fx_common/fx_pixels.c",
        "modules/glock/gl_review.c", "modules/glock/gl_format.c", "-o", "build/tests/module-lifecycle")
    run("build/tests/module-lifecycle")
    run("gcc", *flags, "-Wno-unused-function", "-Wno-unused-parameter", "-ffunction-sections", "-fdata-sections",
        "-Wl,--gc-sections", "-include", "modules/fx_common/fx_namespace.h", "-DFX_MIRROR_UI_HOST_TEST", "tests/capture_error_status.c", "modules/glock/gl_format.c",
        "-o", "build/tests/capture-error-status")
    run("build/tests/capture-error-status")
    run("gcc", *flags, "-Wno-unused-function", "-Wno-unused-parameter", "-ffunction-sections", "-fdata-sections",
        "-Wl,--gc-sections", "-DFX_MIRROR_UI_HOST_TEST", "tests/shutter_event_dispatch.c", "-o", "build/tests/shutter-event-dispatch")
    run("build/tests/shutter-event-dispatch")
    run("gcc", *flags, "-DMIRROR_CAMERA_HOST_TEST", "-DFX_GATE_HOST_TEST", "-DFX_TRACE_HOST_TEST",
        "tests/camera_portability.c", "modules/mirror/mirror_camera.c", "modules/mirror/mirror_capture_gate.c",
        "modules/mirror/mirror_raw_trace.c", "modules/fx_common/fx_mirror_raw.c", "modules/fx_common/fx_mirror_sensor.c", "modules/fx_common/fx_mirror_registered.c",
        "-o", "build/tests/camera")
    run("build/tests/camera")
    run("build/tests/camera", "bad-rom")
    run("build/tests/camera", "bad-stage")
    run("build/tests/camera", "raw")
    run("gcc", *flags, "-DMIRROR_70D_RESEARCH", "-DMIRROR_CAMERA_HOST_TEST", "-DFX_GATE_HOST_TEST", "-DFX_TRACE_HOST_TEST",
        "tests/camera_portability.c", "modules/mirror/mirror_camera.c", "modules/mirror/mirror_capture_gate.c",
        "modules/mirror/mirror_raw_trace.c", "modules/fx_common/fx_mirror_raw.c", "modules/fx_common/fx_mirror_sensor.c", "modules/fx_common/fx_mirror_registered.c",
        "-o", "build/tests/camera-70d")
    run("build/tests/camera-70d", "70d")
    run("build/tests/camera-70d", "70d-guards")
    run("gcc", *flags, "-include", "modules/fx_common/fx_namespace.h", "-DFX_HOST_TEST",
        "tests/preview_portability.c", "tests/preview_sdk.c", "modules/fx_common/fx_camera.c", "modules/mirror/mirror_driver.c",
        "modules/fx_common/fx_mirror.c", "modules/fx_common/fx_pixels.c", "modules/glock/gl_review.c",
        "modules/glock/gl_format.c", "-o", "build/tests/preview")
    run("build/tests/preview")
    run("gcc", *flags, "-include", "modules/fx_common/fx_namespace.h", "-DFX_HOST_TEST",
        "-DMIRROR_CAMERA_HOST_TEST", "-DFX_GATE_HOST_TEST", "-DFX_TRACE_HOST_TEST", "-DFX_REGISTERED_TEST_HOOK",
        "tests/capture_delivery.c", "tests/preview_sdk.c", "modules/fx_common/fx_camera.c",
        "modules/mirror/mirror_camera.c", "modules/mirror/mirror_capture_gate.c", "modules/mirror/mirror_raw_trace.c",
        "modules/mirror/mirror_driver.c", "modules/fx_common/fx_mirror.c", "modules/fx_common/fx_mirror_raw.c",
        "modules/fx_common/fx_mirror_sensor.c", "modules/fx_common/fx_mirror_registered.c", "modules/fx_common/fx_pixels.c", "modules/glock/gl_review.c",
        "modules/glock/gl_format.c", "-o", "build/tests/capture-delivery")
    run("build/tests/capture-delivery")
    run("build/tests/capture-delivery", "held-shutdown")

if __name__ == "__main__":
    main()
