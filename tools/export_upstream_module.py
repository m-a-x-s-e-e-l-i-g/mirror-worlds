"""Export and clean-build the self-contained Mirror subtree for upstream review.

Creates local source/patch artifacts only; never opens a PR or modifies ML core.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

from tools.audit_module import inspect_module
from tools.build_module import UPSTREAM_REVISION, DEFAULT_SOURCE_DATE_EPOCH, normalize_module_metadata, audit_module_headers
from tools.linux_runtime import LinuxRuntime
from tools.reproducible_zip import member_name, write_archive

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def module_inputs(stage):
    """Follow only objects in the default Makefile, ignoring stale dependency files."""
    stage = Path(stage).resolve()
    source = stage.parents[1]
    text = (stage / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^MODULE_OBJS\s*=\s*(.+)$", text, re.M)
    if not match:
        raise ValueError("Missing explicit default module object list")
    objects = re.findall(r"\$\(BUILD_DIR\)/(\w+)\.o", match[1])
    if not objects or len(objects) != len(set(objects)):
        raise ValueError("Invalid default module objects")
    paths = {"Makefile", "README.rst", "mirror_native_disabled.c"}
    for name in objects:
        dependency = stage / "build" / (name + ".d")
        tokens = dependency.read_text(encoding="utf-8").replace("\\\n", " ").split()
        for token in tokens:
            if token.endswith(":"):
                continue
            path = (stage / token).resolve()
            if path.is_relative_to(stage):
                relative = path.relative_to(stage).as_posix()
                if not relative.startswith("build/"):
                    paths.add(relative)
            elif not any(path.is_relative_to(source / part) for part in ("src", "include")):
                raise ValueError("Module dependency crosses the generic SDK boundary: " + token)
    for name in paths:
        member_name(name)
        if not (stage / name).is_file():
            raise ValueError("Missing staged module input: " + name)
    return sorted(paths)


def new_file_patch(name, data):
    name = member_name(name)
    blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
    header = f"diff --git a/{name} b/{name}\nnew file mode 100644\nindex {'0'*40}..{blob}\n"
    if not data:
        return header
    text = data.decode("utf-8")
    if not text.endswith("\n"):
        raise ValueError("Patch input requires a final newline")
    lines = text.splitlines(keepends=True)
    return header + f"--- /dev/null\n+++ b/{name}\n@@ -0,0 +1,{len(lines)} @@\n" + "".join("+" + line for line in lines)


def original_input(name):
    if name.startswith("shared/"):
        return "modules/fx_common/" + name.removeprefix("shared/")
    if name == "engine/glitchlock.h":
        return "core/glitchlock.h"
    if name.startswith("engine/"):
        return "modules/glock/" + name.removeprefix("engine/")
    return "modules/mirror/" + name


def clean_build(output):
    """Linux side: a new native checkout, patched and built independently."""
    output = Path(output).resolve()
    plan = json.loads((output / "plan.json").read_text())
    archive = ROOT / plan["upstream_source_archive"]
    if digest(archive.read_bytes()) != plan["upstream_source_archive_sha256"]:
        raise ValueError("Pinned upstream archive changed")
    parent = Path.home() / ".cache/mirror-worlds/upstream-review"
    parent.mkdir(parents=True, exist_ok=True)
    checkout = Path(tempfile.mkdtemp(prefix="mirror-", dir=parent))
    with tarfile.open(archive) as tar:
        tar.extractall(checkout, filter="data")
    patch = output / "mirror-upstream.patch"
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=checkout, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=checkout, check=True)
    stage = checkout / "modules/mirror"
    for name, expected in plan["export_files"].items():
        if digest((stage / name).read_bytes()) != expected:
            raise ValueError("Applied patch differs from exported source: " + name)
    subprocess.run(["make", "-B", "build/module_strings.h"], cwd=stage, check=True)
    normalize_module_metadata(stage / "build/module_strings.h", plan["source_date_epoch"])
    subprocess.run(["make", "-j2", "FATAL_WARNINGS=y"], cwd=stage, check=True)
    subprocess.run(["make", "build/mirror.debug.o", "FATAL_WARNINGS=y"], cwd=stage, check=True)
    audit_module_headers(stage)
    for name in ("mirror.mo", "mirror.debug.o"):
        shutil.copyfile(stage / "build" / name, output / name)
    compiler = subprocess.check_output(["arm-none-eabi-gcc", "--version"], text=True).splitlines()[0]
    (output / "clean-build.json").write_text(json.dumps({"checkout": str(checkout), "compiler": compiler,
        "git_apply_check_passed": True, "compiler_header_boundary_passed": True}, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--distro", default="Ubuntu")
    args = parser.parse_args()
    source = ROOT / ".cache/ml-upstream"
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != UPSTREAM_REVISION:
        raise ValueError("Pinned upstream source revision mismatch")
    subprocess.run(["git", "-C", str(source), "diff", "--quiet", "HEAD", "--"], check=True)
    manifest = json.loads((ROOT / "build/upstream/mirror/build.json").read_text(encoding="utf-8"))
    if manifest.get("research_70d"):
        raise ValueError("Export requires the normal universal module")
    for name, expected in manifest["source_files"].items():
        if digest((ROOT / name).read_bytes()) != expected:
            raise ValueError("Source changed since module build: " + name)
    module = ROOT / "build/upstream/mirror/mirror.mo"
    if digest(module.read_bytes()) != manifest["files"]["mirror.mo"]:
        raise ValueError("Candidate changed since build")
    output = (args.output or ROOT / "build/upstream-export" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    if not output.is_relative_to(ROOT / "build/upstream-export"):
        raise ValueError("Exports must stay under build/upstream-export")
    output.mkdir(parents=True, exist_ok=False)
    stage = source / "modules/mirror"
    files = {}
    for name in module_inputs(stage):
        original = original_input(name)
        data = (ROOT / original).read_bytes()
        if digest(data) != manifest["source_files"].get(original) or (stage / name).read_bytes() != data:
            raise ValueError("Staged export differs from audited source: " + name)
        data = data.replace(b"\r\n", b"\n")
        if data and not data.endswith(b"\n"):
            data += b"\n"
        target = output / "source/modules/mirror" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files[name] = digest(data)
    patch = "".join(new_file_patch("modules/mirror/" + name, (output / "source/modules/mirror" / name).read_bytes()) for name in files)
    (output / "mirror-upstream.patch").write_text(patch, encoding="utf-8", newline="\n")
    archive = ROOT / ".cache" / ("ml-core-source-" + UPSTREAM_REVISION + ".tar")
    subprocess.run(["git", "-C", str(source), "archive", "--format=tar", "--output", str(archive), UPSTREAM_REVISION], check=True)
    plan = {"upstream_revision": revision, "module_sha256": digest(module.read_bytes()), "version": manifest["version"],
            "source_date_epoch": manifest.get("source_date_epoch", DEFAULT_SOURCE_DATE_EPOCH), "export_files": files,
            "upstream_source_archive": archive.relative_to(ROOT).as_posix(), "upstream_source_archive_sha256": digest(archive.read_bytes())}
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(ROOT / "tools/export_upstream_module.py", output / "export_upstream_module.py")
    shutil.copyfile(ROOT / "docs/upstream-contribution.md", output / "README.md")
    runtime = LinuxRuntime(ROOT, "wsl", distro=args.distro)
    relative = output.relative_to(ROOT).as_posix()
    with (output / "build.log").open("w", encoding="utf-8") as log:
        runtime.run("python3", "-c", "from pathlib import Path;from tools.export_upstream_module import clean_build;clean_build(Path(" + repr(relative) + "))", stdout=log, stderr=subprocess.STDOUT)
    data = (output / "mirror.mo").read_bytes()
    audit = inspect_module(data)
    if digest(data) != plan["module_sha256"] or audit["unregistered_property_handlers"]:
        raise ValueError("Standalone export does not reproduce the audited candidate")
    result = {"kind": "self-contained-upstream-module-export", "version": plan["version"], "upstream_revision": revision,
              "module_sha256": digest(data), "matches_normal_candidate": True, "imports_checked": len(audit["imports"]),
              "clean_build": json.loads((output / "clean-build.json").read_text()), "export_files": files,
              "evidence_limit": "Independent clean source build only. Retains the candidate's existing firmware and hardware limitations.",
              "artifact_files": {p.relative_to(output).as_posix(): digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}}
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    bundle = output / "bundle"
    shutil.copytree(output / "source", bundle / "source")
    for name in ("mirror-upstream.patch", "results.json", "plan.json", "README.md"):
        shutil.copyfile(output / name, bundle / name)
    shutil.copyfile(ROOT / "COPYING", bundle / "COPYING")
    zip_path = write_archive(bundle, output / ("MIRROR-" + manifest["version"] + "-UPSTREAM-SOURCE.zip"), plan["source_date_epoch"])
    print("Clean upstream build reproduces candidate:", result["module_sha256"])
    print("Self-contained source files:", len(files))
    print("Review bundle:", zip_path)


if __name__ == "__main__":
    main()
