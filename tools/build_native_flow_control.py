"""Build the unshipped native-capture regression helper from an exact module cohort."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from tools.build_module import UPSTREAM_REVISION, DEFAULT_SOURCE_DATE_EPOCH, normalize_module_metadata, audit_module_headers
from tools.linux_runtime import LinuxRuntime

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mirror-build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    mirror = args.mirror_build.resolve()
    output = args.output.resolve()
    if not mirror.is_relative_to(ROOT / "build/research") or not output.is_relative_to(ROOT / "build/research"):
        parser.error("Native research builds must stay under build/research")
    if output.exists():
        raise FileExistsError(output)
    manifest = json.loads((mirror / "build.json").read_text(encoding="utf-8"))
    if not manifest["research_70d"] or digest(mirror / "mirror.mo") != manifest["files"]["mirror.mo"]:
        raise ValueError("Expected a verified isolated main-module research build")
    source = ROOT / ".cache/ml-upstream"
    if subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() != UPSTREAM_REVISION:
        raise ValueError("Unexpected ML source revision")
    stage = source / "modules" / ("mflow_" + output.name.replace("-", "_"))
    stage.mkdir(exist_ok=False)
    inputs = {}
    for name, expected in manifest["source_files"].items():
        path = ROOT / name
        if digest(path) != expected:
            raise ValueError("Main-module source changed: " + name)
        if path.suffix != ".h":
            continue
        folder = "shared" if name.startswith("modules/fx_common/") else "engine" if name.startswith(("core/", "modules/glock/")) else ""
        destination = stage / folder / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        inputs[name] = expected
    for path in (ROOT / "tests/qemu_native_flow").iterdir():
        if path.is_file():
            shutil.copyfile(path, stage / path.name)
            inputs[path.relative_to(ROOT).as_posix()] = digest(path)
    runtime = LinuxRuntime(ROOT, "wsl", wsl_user="root")
    relative = stage.relative_to(ROOT).as_posix()
    runtime.run("make", "-B", "build/module_strings.h", cwd=relative)
    normalize_module_metadata(stage / "build/module_strings.h", DEFAULT_SOURCE_DATE_EPOCH)
    runtime.run("make", "-j2", "FATAL_WARNINGS=y", cwd=relative)
    audit_module_headers(stage)
    imports = set((stage / "build/mflow.dep").read_text().splitlines())
    symbols = {line.split()[1] for line in (mirror / "mirror.sym").read_text().splitlines() if len(line.split()) == 2}
    core = ROOT / ".cache/70d-probe/card/ML/modules/70D_112.sym"
    exports = {line.split()[1] for line in core.read_text().splitlines() if len(line.split()) == 2}
    if not imports <= symbols | exports:
        raise ValueError("Unresolved helper imports: " + str(imports - symbols - exports))
    output.mkdir(parents=True)
    for name in ("mflow.mo", "mflow.sym", "mflow.dep", "mflow.o"):
        shutil.copyfile(stage / "build" / name, output / name)
    for name, expected in inputs.items():
        destination = output / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
        assert digest(destination) == expected
    report = {"kind": "unshipped-native-flow-control", "ml_revision": UPSTREAM_REVISION,
              "mirror_sha256": manifest["files"]["mirror.mo"], "imports": sorted(imports),
              "core_symbols_sha256": digest(core), "hardware_test": False, "source_files": inputs,
              "files": {p.relative_to(output).as_posix(): digest(p) for p in output.rglob("*") if p.is_file()}}
    (output / "build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Native flow helper:", len(imports), "imports resolved;", output / "mflow.mo")


if __name__ == "__main__":
    main()
