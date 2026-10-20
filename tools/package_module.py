"""Package an audited module with a reproducible archive and no replacement core."""
import argparse
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


def package_module(module_name, instructions=None, root=ROOT):
    root = Path(root).resolve()
    if module_name not in MODULES:
        raise ValueError("Unknown module")
    build = root / ("build/module" if module_name == "glock" else "build/modules/" + module_name)
    manifest_bytes = (build / "build.json").read_bytes()
    manifest = json.loads(manifest_bytes)
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
    releases = root / "releases"
    release = releases / (version if module_name == "glock" else module_name + "-" + version)
    title = "GLITCHLOCK" if module_name == "glock" else module_name.upper()
    package = releases / f"{title}-{version}-EOSM202.zip"
    for path in (release, package):
        if path.exists() or path.is_symlink():
            raise FileExistsError("Refusing to replace a published release: " + str(path))
    files = {"ML/MODULES/" + module_name + ".mo": build / (module_name + ".mo"), "BUILD.json": build / "build.json",
             "README.md": instructions, "COPYING": root / "COPYING", "source/COPYING": root / "COPYING",
             module_name + ".dep": build / (module_name + ".dep"), "elf-report.txt": build / "elf-report.txt"}
    for path in manifest["source_files"]:
        files["source/" + path] = source_file(root, path)
    for path in ("tools/build_module.py", "tools/audit_module.py", "tools/package_module.py", "tools/reproducible_zip.py",
                 "tools/ml-builder.Dockerfile", "targets/EOSM.202/EOSM_202.sym", "targets/EOSM.202/PROVENANCE.md"):
        files["source/" + path] = source_file(root, path)
    if module_name != "glock":
        files["source/tools/audit_module_set.py"] = source_file(root, "tools/audit_module_set.py")
    if module_name == "mirror":
        for name in ("analyze_mirror_native_patch.py", "analyze_mirror_capture_gate.py", "analyze_mirror_native_trace.py"):
            path = "tools/" + name
            files["source/" + path] = source_file(root, path)
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
                  "target": "EOSM202", "compression": "stored", "member_mode": "100644",
                  "timestamp": "UTC DOS timestamp, rounded down to an even second"}
        (release / "PACKAGE.json").write_text(json.dumps(recipe, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
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
    args = parser.parse_args()
    instructions = args.instructions.resolve() if args.instructions is not None else None
    package = package_module(args.module, instructions)
    print(package)
    print("SHA256 " + digest(package))


if __name__ == "__main__":
    main()
