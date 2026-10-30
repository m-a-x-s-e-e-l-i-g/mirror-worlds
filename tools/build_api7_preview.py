"""Build an isolated preview-only module with the real historical API-7 SDK.

This never replaces a normal candidate, installs a core or requests a ROM.
The SDK is data: no downloaded Makefile or script is executed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request
import zipfile

from tools.audit_camera_cores import parse_exports
from tools.audit_module import inspect_module
from tools.camera_abi import compare_abi, inspect_abi
from tools.linux_runtime import LinuxRuntime
from tools.reproducible_zip import write_archive

ROOT = Path(__file__).resolve().parents[1]
SDK_REVISION = "dc3d012aff3ddc0e07df3ceafb9b95dbfdf56f12"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fetch_sdk(manifest):
    if (manifest["repository"] != "ryulin456/magiclantern-zh" or manifest["revision"] != SDK_REVISION
            or manifest["prefix"] != "source/work/src-lua-fix-zh"):
        raise ValueError("Historical SDK provenance mismatch")
    cache = ROOT / ".cache/api7-source"

    def fetch(item):
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in item["path"]:
            raise ValueError("Unsafe SDK path")
        path = cache / relative
        url = "https://raw.githubusercontent.com/" + manifest["repository"] + "/" + SDK_REVISION + "/" + manifest["prefix"] + "/" + relative.as_posix()
        if path.exists():
            data = path.read_bytes()
        else:
            with urllib.request.urlopen(url, timeout=45) as response:
                data = response.read(item["size"] + 1)
        blob = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        if len(data) != item["size"] or hashlib.sha1(blob).hexdigest() != item["sha"]:
            raise ValueError("Historical SDK blob changed: " + relative.as_posix())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {**item, "sha256": sha(data), "source_url": url}

    with ThreadPoolExecutor(max_workers=6) as pool:
        files = list(pool.map(fetch, manifest["files"]))
    return cache, {**manifest, "files": files}


def compile_variant(output):
    """Linux side. Build from the frozen local source and SDK copies."""
    output = Path(output).resolve()
    source, sdk = output / "sources", output / "sdk"
    flags = ["-Os", "-g3", "-std=gnu99", "-march=armv5te", "-mlong-calls", "-D__ARM__", "-DMODULE",
             "-DMODULE_NAME=mirror", "-DCONFIG_MAGICLANTERN", "-DMIRROR_RELEASE", "-DMIRROR_PREVIEW_ONLY",
             "-DFX_PREFIX=mirror", "-fno-strict-aliasing", "-fno-common", "-fno-builtin-printf",
             "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-format",
             "-include", str(source / "modules/fx_common/fx_namespace.h")]
    for directory in (sdk / "src", sdk / "platform/all", output,
                      source / "modules/mirror", source / "modules/fx_common", source / "modules/glock", source / "core"):
        flags.append("-I" + str(directory))
    files = ["modules/mirror/" + f + ".c" for f in ("mirror", "mirror_camera", "mirror_driver", "mirror_settings", "mirror_native_disabled")]
    files += ["modules/fx_common/" + f + ".c" for f in ("fx_camera", "fx_mirror", "fx_mirror_raw", "fx_mirror_sensor", "fx_pixels")]
    files += ["modules/glock/" + f + ".c" for f in ("gl_format", "gl_review")]
    objects = []
    for filename in files:
        obj = output / (Path(filename).stem + ".o")
        subprocess.run(["arm-none-eabi-gcc", *flags, "-MMD", "-MF", str(obj.with_suffix(".d")),
                        "-c", str(source / filename), "-o", str(obj)], check=True)
        objects.append(str(obj))
        deps = obj.with_suffix(".d").read_text()
        if re.search(r"platform/(?!all/)", deps) or ".cache/ml-upstream" in deps or ".cache/magiclantern" in deps:
            raise ValueError("API-7 build leaked camera-specific or API-8 headers")
    subprocess.run(["arm-none-eabi-ld", "-r", "-o", str(output / "mirror.debug.o"), *objects], check=True)
    subprocess.run(["arm-none-eabi-objcopy", "--strip-debug", "--strip-unneeded", str(output / "mirror.debug.o"), str(output / "mirror.mo")], check=True)
    # Independently compile the SDK types, rather than reuse candidate types.
    probe = output / "abi-probe.c"
    probe.write_text("#include <module.h>\n#include <dryos.h>\n#include <menu.h>\n#include <lens.h>\n#include <vram.h>\n#include <config.h>\n" +
                     "\n".join("struct " + name + " probe_" + name + ";" for name in
                                ("vram_info", "lens_info", "config_var", "display_filter_buffers", "menu_entry", "menu_display_info")))
    subprocess.run(["arm-none-eabi-gcc", *flags, "-c", str(probe), "-o", str(output / "abi-probe.o")], check=True)
    layouts = compare_abi(inspect_abi(output / "mirror.debug.o"), inspect_abi(output / "abi-probe.o"))
    (output / "sdk-layout-audit.json").write_text(json.dumps(layouts, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--distro", default="Ubuntu")
    args = parser.parse_args()
    output = (args.output or ROOT / "build/research/api7-preview" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    if not output.is_relative_to(ROOT / "build/research"):
        raise ValueError("Experimental API-7 outputs must stay under build/research")
    manifest = json.loads((ROOT / "targets/api7-sdk-inputs.json").read_text(encoding="utf-8"))
    sdk, receipt = fetch_sdk(manifest)
    output.mkdir(parents=True, exist_ok=False)
    for item in receipt["files"]:
        dest = output / "sdk" / item["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sdk / item["path"], dest)
    for folder in ("modules/mirror", "modules/fx_common", "modules/glock", "core"):
        for path in (ROOT / folder).rglob("*"):
            if path.suffix not in (".c", ".h", ".inc") or "build" in path.relative_to(ROOT / folder).parts:
                continue
            dest = output / "sources" / path.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
    for filename in ("tools/build_api7_preview.py", "tools/audit_module.py", "tools/camera_abi.py",
                     "targets/api7-sdk-inputs.json", "targets/distribution-inputs.json", "docs/api7-preview-test.md"):
        dest = output / "sources" / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / filename, dest)
    (output / "sdk-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(ROOT / "docs/api7-preview-test.md", output / "README-TEST.md")
    (output / "module_strings.h").write_text('#define MODULE_STRINGS() MODULE_STRINGS_START() \\\nMODULE_STRING("Name","Mirror Worlds") \\\nMODULE_STRING("Author","Max Seelig (MAXmade)") \\\nMODULE_STRING("License","GPL-2.0-or-later") \\\nMODULE_STRING("Summary","Experimental API-7 preview only; photos stay original") \\\nMODULE_STRINGS_END()\n', encoding="utf-8")
    runtime = LinuxRuntime(ROOT, "wsl", distro=args.distro)
    relative = output.relative_to(ROOT).as_posix()
    with (output / "build.log").open("w", encoding="utf-8") as log:
        runtime.run("python3", "-c", "from pathlib import Path;from tools.build_api7_preview import compile_variant;compile_variant(Path(" + repr(relative) + "))", stdout=log, stderr=subprocess.STDOUT)
    data = (output / "mirror.mo").read_bytes()
    module = inspect_module(data, api_major=7)
    if module["unregistered_property_handlers"]:
        raise ValueError("Unregistered API-7 property handlers")
    # Compare with the exact pinned public 7D distribution; no core is installed.
    record = next(r for r in json.loads((ROOT / "targets/distribution-inputs.json").read_text())["archives"] if r["target"] == "7D.203")
    archive = (ROOT / record["local_path"]).read_bytes()
    if sha(archive) != record["sha256"]:
        raise ValueError("7D distribution changed")
    with zipfile.ZipFile(record["local_path"]) as z:
        table = z.read("ML/modules/7D_203.sym")
    (output / "7D_203.sym").write_bytes(table)
    missing = sorted(set(module["imports"]) - parse_exports(table).keys())
    layouts = json.loads((output / "sdk-layout-audit.json").read_text())
    if missing or layouts["result"] != "checked_layouts_match":
        raise ValueError("API-7 imports or SDK fields do not match")
    result = {"kind": "experimental-api7-preview-build", "module_sha256": sha(data), "module_api": module["module_api"],
              "imports": module["imports"], "missing_imports": missing, "checked_sdk_layouts": layouts,
              "audited_distribution": {"target": "7D.203", "sha256": record["sha256"], "symbol_table_sha256": sha(table)},
              "preview_only": True, "native_capture": False, "module_load_verified": False, "hardware_verified": False,
              "evidence_limit": "Historical SDK/export checks only. No actual 7D core layout, module initialization, preview delivery, RAW workflow or camera validation.",
              "artifact_files": {p.relative_to(output).as_posix(): sha(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}}
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    package = output / "candidate"
    (package / "ML/MODULES").mkdir(parents=True)
    shutil.copyfile(output / "mirror.mo", package / "ML/MODULES/mirror.mo")
    for name in ("README-TEST.md", "results.json", "sdk-receipt.json", "sdk-layout-audit.json", "7D_203.sym"):
        shutil.copyfile(output / name, package / name)
    shutil.copytree(output / "sources", package / "source")
    shutil.copytree(output / "sdk", package / "sdk")
    package_files = {p.relative_to(package).as_posix(): sha(p.read_bytes()) for p in sorted(package.rglob("*")) if p.is_file()}
    (package / "PACKAGE.json").write_text(json.dumps({"kind": "experimental-api7-preview-candidate", "target": "7D.203",
        "module_api": [90, 7, 0, 0], "preview_only": True, "native_capture": False, "hardware_verified": False,
        "files": package_files}, indent=2) + "\n", encoding="utf-8")
    archive_path = write_archive(package, output / "MIRROR-API7-7D-PREVIEW-EXPERIMENT.zip", 1792368000)
    print("API 7.0 preview-only module:", output / "mirror.mo")
    print(len(module["imports"]), "imports resolve; 23 SDK fields match; runtime unverified")
    print("Experimental candidate:", archive_path)


if __name__ == "__main__":
    main()
