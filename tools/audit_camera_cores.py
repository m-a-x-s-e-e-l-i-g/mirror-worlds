"""Build the eligible ML cores and check the candidate's imports against each one.

This is a source-build compatibility audit, not a test of installed camera builds.
Native Linux staging avoids slow Git scans and CRLF shebangs on Windows mounts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.audit_module import inspect_module
from tools.build_module import UPSTREAM_REVISION
from tools.camera_matrix import active_defines, load_scope, module_profiles
from tools.camera_abi import compare_abi
from tools.linux_runtime import LinuxRuntime

ROOT = Path(__file__).resolve().parents[1]


def parse_exports(data):
    exports = {}
    for line in data.decode("ascii").splitlines():
        fields = line.split()
        if len(fields) != 2 or fields[1] in exports:
            raise ValueError("Malformed or duplicate core export")
        exports[fields[1]] = int(fields[0], 16)
    return exports


def audit_imports(module, table):
    report = inspect_module(module)
    exports = parse_exports(table)
    missing = sorted(set(report["imports"]) - exports.keys())
    return {"module_sha256": hashlib.sha256(module).hexdigest(),
            "symbol_table_sha256": hashlib.sha256(table).hexdigest(),
            "imports_checked": len(report["imports"]), "missing_imports": missing,
            "result": "unresolved_imports" if missing else "imports_resolve",
            "module_load_verified": False, "native_capture_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=("wsl", "docker"), default="wsl")
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--models", nargs="+", help="Optional subset of eligible models")
    parser.add_argument("--reuse-cores", action="store_true", help="Re-audit the current module against hash-verified existing cores without rebuilding them")
    args = parser.parse_args()
    source = ROOT / ".cache/ml-upstream"
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != UPSTREAM_REVISION:
        raise ValueError("ML source revision mismatch")
    scope = {m["model"] for m in load_scope(ROOT / "targets/official-cameras.json")["models"]}
    profiles = module_profiles(ROOT / "modules/mirror/mirror_camera.c")
    eligible = {p["model"] for p in profiles}
    if args.models and not set(args.models) <= eligible:
        raise ValueError("Requested model is not an eligible module profile")
    targets = []
    for profile in profiles:
        if args.models and profile["model"] not in args.models:
            continue
        target = profile["model"] + "." + profile["firmware"].replace(".", "")
        if profile["model"] not in scope or "CONFIG_DISPLAY_FILTERS" not in active_defines(source / "platform" / target / "internals.h"):
            raise ValueError("Target is outside the approved LiveView-effect scope")
        targets.append(target)
    output = ROOT / "build/camera-cores"
    output.mkdir(parents=True, exist_ok=True)
    archive = ROOT / ".cache" / ("ml-core-source-" + revision + ".tar")
    subprocess.run(["git", "-C", str(source), "archive", "--format=tar", "--output", str(archive), revision], check=True)
    candidate_paths = {"legacy": "build/modules/mirror/mirror.mo", "upstream": "build/upstream/mirror/mirror.mo"}
    candidates = {name: (ROOT / path).read_bytes() for name, path in candidate_paths.items()}
    plan = {"revision": revision, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "reuse_cores": args.reuse_cores,
            "targets": targets, "candidates": {name: {"path": path, "sha256": hashlib.sha256(candidates[name]).hexdigest()}
                                                  for name, path in candidate_paths.items()}}
    for candidate in plan["candidates"].values():
        debug = str(Path(candidate["path"]).with_suffix(".debug.o")).replace("\\", "/")
        candidate["debug_path"] = debug
        candidate["debug_sha256"] = hashlib.sha256((ROOT / debug).read_bytes()).hexdigest()
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    runtime = LinuxRuntime(ROOT, args.runtime, "glitchlock-ml-builder:bookworm", args.distro)
    runtime.run("python3", "tools/build_camera_cores_linux.py", archive.relative_to(ROOT).as_posix(),
                "build/camera-cores/plan.json", "build/camera-cores")
    builds = json.loads((output / "builds.json").read_text(encoding="utf-8"))
    for record in builds["targets"]:
        if record["build_result"] != "passed":
            continue
        table = (output / record["target"] / "magiclantern.sym").read_bytes()
        if hashlib.sha256(table).hexdigest() != record["symbol_table_sha256"]:
            raise ValueError("Core export table changed after build")
        record["candidate_audits"] = {name: audit_imports(data, table) for name, data in candidates.items()}
        for name, audit in record["candidate_audits"].items():
            audit["checked_struct_layouts"] = compare_abi(builds["candidate_layouts"][name], record["core_layouts"])
    builds["evidence_limit"] = "Locally built pinned ML cores, not shipped/installed builds. Resolved symbol names do not establish ABI compatibility, module loading, RAW ownership or hardware support."
    (output / "import-audit.json").write_text(json.dumps(builds, indent=2) + "\n", encoding="utf-8")
    for record in builds["targets"]:
        results = ", ".join(name + ": " + audit["result"] for name, audit in record.get("candidate_audits", {}).items())
        print(record["target"] + ": " + record["build_result"] + ("; " + results if results else ""))


if __name__ == "__main__":
    main()
