"""Package an audited module with a reproducible archive and no replacement core."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil

if __package__:
    from .audit_module import audit
    from .reproducible_zip import PROFILE, member_name, write_archive, zip_time
else:
    from audit_module import audit
    from reproducible_zip import PROFILE, member_name, write_archive, zip_time

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("glock", "slitscan", "mirror", "feedback", "fragment", "diffract")


def source_file(root, name):
    path = root / member_name(name)
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Missing or external package input: " + name)
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def complete_python_sources(files, root):
    """Follow local Python imports without executing package or downloaded code."""
    root = Path(root).resolve()
    pending = [path for name, path in files.items() if name.startswith("source/") and name.endswith(".py")]
    seen = set()
    while pending:
        path = Path(pending.pop()).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Python package source escapes workspace")
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imports = []
            if isinstance(node, ast.Import):
                imports = [(alias.name, 0) for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [(node.module or "", node.level)]
                # Handle 'from . import helper' and namespace-package imports.
                imports += [(".".join(filter(None, (node.module, alias.name))), node.level) for alias in node.names if alias.name != "*"]
            for module, level in imports:
                if level:
                    base = path.parent
                    for _ in range(level - 1):
                        base = base.parent
                    if not base.is_relative_to(root):
                        raise ValueError("Relative Python import escapes workspace")
                    bases = [base]
                else:
                    bases = [root, path.parent]
                found = False
                for base in bases:
                    stem = base.joinpath(*module.split(".")) if module else base
                    candidates = [stem.with_suffix(".py"), stem / "__init__.py"] if module else [stem / "__init__.py"]
                    for candidate in candidates:
                        if candidate.is_file():
                            name = candidate.relative_to(root).as_posix()
                            source = source_file(root, name)
                            files["source/" + name] = source
                            pending.append(source)
                            found = True
                            break
                    if found:
                        break
                    if stem.is_dir():
                        found = True  # A namespace package need not have __init__.py.
                # Imported attributes (e.g. pathlib.Path) are not modules.
                required = isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom) and module == (node.module or "")
                local_name = module.split(".")[0] in ("tools", "scripts", "tests")
                if not found and required and (level or local_name):
                    raise ValueError("Missing local Python package dependency: " + module)
    return files


def package_module(module_name, instructions=None, root=ROOT, candidate=False, matrix_report=None, package_revision=None, arm_binary_report=None):
    root = Path(root).resolve()
    if module_name not in MODULES:
        raise ValueError("Unknown module")
    if package_revision is not None and (type(package_revision) is not int or not 1 <= package_revision <= 99):
        raise ValueError("Package revision must be an integer from 1 through 99")
    build = root / ("build/module" if module_name == "glock" else "build/modules/" + module_name)
    manifest_bytes = (build / "build.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("research_70d") or manifest.get("kind") == "emulator-only-70d-module":
        raise RuntimeError("The unshipped 70D research module cannot be packaged as a camera candidate")
    for name, expected in manifest["files"].items():
        if digest(source_file(build, name)) != expected:
            raise RuntimeError(f"Build artifact changed since manifest generation: {name}")
    for name, expected in manifest["source_files"].items():
        if digest(source_file(root, name)) != expected:
            raise RuntimeError(f"Source changed since the module build: {name}")
    report = audit(build / (module_name + ".mo"), root / ".cache/magiclantern.2025-06-20.EOSM.202.zip",
                   root / "targets/EOSM.202/EOSM_202.sym")
    if digest(root / "targets/EOSM.202/EOSM_202.sym") != report["symbol_table_sha256"]:
        raise RuntimeError("Packaged symbol table differs from the audited target")
    if report["missing_imports"]:
        raise RuntimeError("Refusing to package unresolved imports")
    if report["module_name"] != module_name or manifest["module"] != module_name + ".mo":
        raise RuntimeError("Module identity mismatch")
    if report["unregistered_property_handlers"]:
        raise RuntimeError("Refusing to package defined but unregistered property handlers")
    if not manifest["verification"]["exact_installed_core_imports"]:
        raise RuntimeError("Build manifest is missing its completed import audit")
    version = manifest["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", version):
        raise ValueError("Version must be one portable filename component")
    epoch = manifest["source_date_epoch"]
    zip_time(epoch)
    if instructions is None:
        if version != "0.1.0-diag1":
            raise RuntimeError("This development build needs version-specific instructions: --instructions path/to/test.md")
        instructions = root / "docs/diagnostic-test.md"
    instructions = Path(instructions)
    if not instructions.is_absolute():
        instructions = root / instructions
    if not instructions.is_file():
        raise ValueError("Installation/test instruction file not found")
    if candidate and (module_name != "mirror" or "dev" not in version):
        raise ValueError("The portable candidate package requires a Mirror development version")
    releases = root / ("build/candidates" if candidate else "releases")
    revision_suffix = "" if package_revision is None else "-r" + str(package_revision)
    release = releases / ((version if module_name == "glock" else module_name + "-" + version) + revision_suffix)
    title = "GLITCHLOCK" if module_name == "glock" else module_name.upper()
    target_label = "OFFICIAL-LV-CANDIDATE" if candidate else "EOSM202"
    package = releases / f"{title}-{version}-{target_label}{revision_suffix}.zip"
    for path in (release, package):
        if path.exists() or path.is_symlink():
            raise FileExistsError("Refusing to replace a published release: " + str(path))
    files = {"ML/MODULES/" + module_name + ".mo": build / (module_name + ".mo"), "BUILD.json": build / "build.json",
             "README.md": instructions, "COPYING": root / "COPYING", "source/COPYING": root / "COPYING",
             module_name + ".dep": build / (module_name + ".dep"), "elf-report.txt": build / "elf-report.txt"}
    for path in manifest["source_files"]:
        files["source/" + path] = source_file(root, path)
    for path in ("tools/build_module.py", "tools/audit_module.py", "tools/package_module.py", "tools/reproducible_zip.py",
                 "tools/ml-builder.Dockerfile", "tools/linux_runtime.py", "targets/EOSM.202/EOSM_202.sym", "targets/EOSM.202/PROVENANCE.md"):
        files["source/" + path] = source_file(root, path)
    if module_name != "glock":
        files["source/tools/audit_module_set.py"] = source_file(root, "tools/audit_module_set.py")
    if module_name == "mirror":
        for name in ("analyze_mirror_native_patch.py", "analyze_mirror_capture_gate.py", "analyze_mirror_native_trace.py"):
            path = "tools/" + name
            files["source/" + path] = source_file(root, path)
    candidate_metadata = None
    if candidate:
        if __package__:
            from .camera_matrix import load_scope, module_profiles
        else:
            from camera_matrix import load_scope, module_profiles
        scope = load_scope(root / "targets/official-cameras.json")
        profiles = module_profiles(root / "modules/mirror/mirror_camera.c")
        if not {p["model"] for p in profiles} <= {m["model"] for m in scope["models"]}:
            raise ValueError("Candidate profiles exceed the approved camera scope")
        candidate_metadata = {"kind": "unvalidated-camera-candidates", "module_sha256": digest(build / "mirror.mo"),
                              "profiles": profiles, "module_load_verified": False, "hardware_tested": False,
                              "notice": "Native RAW is implemented only for EOSM 2.0.2. Other listed profiles are preview candidates; their saved photos remain original. No new profile is hardware validated."}
        for name in ("targets/official-cameras.json", "targets/camera-source-references.json", "docs/portability.md",
                     "tools/audit_distributions.py", "tools/build_api7_preview.py", "targets/api7-sdk-inputs.json",
                     "targets/distribution-inputs.json", "docs/api7-preview-test.md",
                     "docs/emulation.md", "docs/candidate-test.md", "tools/camera_matrix.py", "tools/build_qemu_eos.py", "tools/camera_abi.py",
                     "tools/audit_camera_cores.py", "tools/build_camera_cores_linux.py", "tools/build_qemu_linux.sh",
                     "tools/qemu-eos.Dockerfile", "tools/qemu_model_inventory.c", "scripts/test_portability.py",
                     "scripts/test_arm_preview.py", "scripts/test_registered_raw.py", "scripts/analyze_cfa_registration.py",
                     "docs/cfa-registration.md", "docs/raw-processing-cost.md", "docs/eosm-raw-bounds.md", "scripts/measure_registered_cost.py",
                     "scripts/verify_release.py", "scripts/test_main_capture_refusal.py", "scripts/test_capture_cancellation.py",
                     "tools/export_upstream_module.py", "docs/upstream-contribution.md",
                     "tools/analyze_qemu_boot.py", "tools/qemu_module_state.gdb.py",
                     "tools/qemu_70d_native.gdb.py", "scripts/test_qemu_lossless.py", "scripts/test_qemu_cr2.py",
                     "tools/build_70d_research.py", "tools/qemu_70d_raw_probe.gdb.py", "tools/freeze_research_receipt.py",
                     "tools/run_camera_matrix.py", "tools/run_camera_matrix_linux.py", "tools/qemu_matrix_state.gdb.py",
                     "tools/build_qemu_control.py", "tests/qemu_control/Makefile", "tests/qemu_control/README.rst",
                     "tools/build_native_flow_control.py", "tools/qemu_native_flow.gdb.py",
                     "tests/qemu_native_flow/Makefile", "tests/qemu_native_flow/README.rst",
                     "scripts/test_70d_raw_probe.py",
                     "targets/70D.112/native-research.json", "targets/70D.112/README.md",
                     "targets/70D.112/emulator-research.md", "targets/70D.112/qemu-capready-experiment.patch",
                     "targets/70D.112/qemu-eeko-color-experiment.patch", "targets/70D.112/qemu-jp57-experiment.patch",
                     "targets/70D.112/qemu/lossless14.c", "targets/70D.112/qemu/jp57_research.c",
                     "targets/70D.112/lcd-research.json", "targets/70D.112/qemu-lcd-experiment.patch",
                     "targets/70D.112/qemu-cr2-experiment.patch", "targets/70D.112/qemu/eeko_lcd_research.inc.c",
                     "targets/70D.112/qemu-cr2-repeat-experiment.patch",
                     "targets/70D.112/qemu-fencing-experiment.patch", "targets/70D.112/fencing-research.json",
                     "targets/70D.112/qemu/fencing_research.inc.c",
                     "targets/70D.112/research/Makefile", "targets/70D.112/research/README.rst",
                     "targets/70D.112/research/m70raw.c", "targets/70D.112/research/raw_contract.h"):
            files["source/" + name] = source_file(root, name)
        for path in (root / "tests").rglob("*"):
            if path.is_file() and path.suffix in (".py", ".h", ".c"):
                name = path.relative_to(root).as_posix()
                files["source/" + name] = source_file(root, name)
        complete_python_sources(files, root)
        # This is evidence for the packaged bytes, not an assertion of support.
        evidence = root / "build/camera-cores/import-audit.json"
        audits = json.loads(evidence.read_text(encoding="utf-8"))
        for record in audits["targets"]:
            if record["build_result"] == "passed":
                if record["candidate_audits"]["legacy"]["module_sha256"] != candidate_metadata["module_sha256"]:
                    raise ValueError("Core audit describes a different candidate")
        if set(r["target"] for r in audits["targets"]) != {p["model"] + "." + p["firmware"].replace(".", "") for p in profiles}:
            raise ValueError("Core audit does not cover the candidate profiles")
        files["CORE-AUDIT.json"] = evidence
        if matrix_report is not None:
            matrix_report = Path(matrix_report)
            if not matrix_report.is_absolute(): matrix_report = root / matrix_report
            matrix = json.loads(matrix_report.read_text(encoding="utf-8"))
            if matrix["kind"] != "automated-universal-module-matrix" or matrix["module"]["sha256"] != candidate_metadata["module_sha256"]:
                raise ValueError("Automated matrix describes a different module")
            if {r["target"] for r in matrix["targets"]} != {p["model"] + "." + p["firmware"].replace(".", "") for p in profiles}:
                raise ValueError("Automated matrix does not cover the candidate profiles")
            for name, expected in matrix["artifact_files"].items():
                if digest(source_file(root, name)) != expected:
                    raise ValueError("Automated matrix evidence changed: " + name)
            files["AUTOMATED-MATRIX.json"] = matrix_report
            candidate_metadata["identical_legacy_upstream_binary"] = matrix["identical_upstream_binary"]
            candidate_metadata["automated_results"] = matrix["counts"]
        if arm_binary_report is not None:
            if __package__:
                from .camera_matrix import attach_arm_binary_fixtures
            else:
                from camera_matrix import attach_arm_binary_fixtures
            arm_binary_report = Path(arm_binary_report)
            if not arm_binary_report.is_absolute(): arm_binary_report = root / arm_binary_report
            arm = json.loads(arm_binary_report.read_text(encoding="utf-8"))
            for name, expected in arm["artifact_files"].items():
                if digest(source_file(root, name)) != expected:
                    raise ValueError("Synthetic ARM evidence changed: " + name)
            for variant in arm["variants"]:
                if arm["artifact_files"].get(variant["module_path"]) != variant["module_sha256"]:
                    raise ValueError("Synthetic ARM module is not bound to its input")
            check = {"counts": {}, "models": [{"model": item["model"], "module_profiles": [p for p in profiles if p["model"] == item["model"]]} for item in scope["models"]]}
            attach_arm_binary_fixtures(check, arm, {"candidate": candidate_metadata["module_sha256"]})
            if check["counts"].get("synthetic_arm_binary_profile_runs_verified") != 60:
                raise ValueError("Synthetic ARM evidence does not cover this candidate")
            files["ARM-BINARY-FIXTURE.json"] = arm_binary_report
            for api in (7, 8):
                for cpu in ("arm946-eos", "arm946-eos5"):
                    name = "api" + str(api) + "/" + cpu + ".log"
                    files["evidence/arm-module/" + name] = source_file(arm_binary_report.parent, name)
            files["evidence/arm-module/api8/corruption-rejected.log"] = source_file(arm_binary_report.parent, "api8/corruption-rejected.log")
            candidate_metadata["synthetic_arm_binary_profile_runs"] = 60
    if len(files) != len({name.casefold() for name in files}):
        raise ValueError("Package input names collide on case-insensitive filesystems")
    # Recheck copied bytes too: a late edit must not silently produce a release
    # inconsistent with its module build or reviewed installation instructions.
    expected_payload = {name: digest(path) for name, path in files.items()}
    expected_payload["BUILD.json"] = hashlib.sha256(manifest_bytes).hexdigest()
    release.mkdir(parents=True, exist_ok=False)
    try:
        for name, source in sorted(files.items()):
            target = release / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if digest(target) != expected_payload[name]:
                raise RuntimeError("Package input changed during copy: " + name)
        for name, expected in manifest["source_files"].items():
            if digest(release / "source" / name) != expected:
                raise RuntimeError("Copied source differs from module build: " + name)
        for name in (module_name + ".mo", module_name + ".dep", "elf-report.txt"):
            target = release / ("ML/MODULES/" + name if name.endswith(".mo") else name)
            if digest(target) != manifest["files"][name]:
                raise RuntimeError("Copied artifact differs from module build: " + name)
        (release / "IMPORTS.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        recipe = {"format": "maxmade.module-package.v1", "archive_profile": PROFILE,
                  "source_date_epoch": epoch, "module": module_name, "version": version,
                  "target": target_label, "compression": "stored", "member_mode": "100644",
                  "timestamp": "UTC DOS timestamp, rounded down to an even second"}
        if package_revision is not None:
            recipe["package_revision"] = package_revision
        (release / "PACKAGE.json").write_text(json.dumps(recipe, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        if candidate_metadata:
            (release / "CAMERAS.json").write_text(json.dumps(candidate_metadata, indent=2) + "\n", encoding="utf-8", newline="\n")
        # This rule travels with the checksummed tree. Git must not normalize
        # copied guides, metadata or pinned upstream bytes on a later checkout.
        (release / ".gitattributes").write_bytes(b"* -text\n")
        hashes = {p.relative_to(release).as_posix(): digest(p) for p in release.rglob("*") if p.is_file()}
        (release / "SHA256SUMS").write_text("".join(f"{value}  {name}\n" for name, value in sorted(hashes.items())), encoding="utf-8", newline="\n")
        write_archive(release, package, epoch)
    except BaseException:
        # Verify the resolved absolute scope before recursively removing only
        # this invocation's newly created, unsuccessful release directory.
        if release.resolve().parent != releases.resolve() or release.is_symlink():
            raise RuntimeError("Refusing cleanup outside the release directory")
        shutil.rmtree(release)
        raise
    return package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instructions", type=Path, help="Reviewed installation/test instructions for this development version")
    parser.add_argument("--module", default="glock", choices=MODULES)
    parser.add_argument("--candidate", action="store_true", help="Prepare the portable Mirror development candidate under build/candidates")
    parser.add_argument("--matrix-report", type=Path, help="Attach hash-verified automated results for these exact module bytes")
    parser.add_argument("--arm-binary-report", type=Path, help="Attach hash-verified synthetic SDK ARM results and logs; no helper executable is packaged")
    parser.add_argument("--package-revision", type=int, help="Create a fresh -rN source/package revision without replacing an existing archive or changing module bytes")
    args = parser.parse_args()
    instructions = args.instructions.resolve() if args.instructions is not None else None
    package = package_module(args.module, instructions, candidate=args.candidate, matrix_report=args.matrix_report, package_revision=args.package_revision, arm_binary_report=args.arm_binary_report)
    print(package)
    print("SHA256 " + digest(package))


if __name__ == "__main__":
    main()
