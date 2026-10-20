"""Build a genuine ML relocatable module in an isolated GNU ARM container."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
if __package__:
    from .audit_module import audit
else:
    from audit_module import audit

ROOT = Path(__file__).resolve().parents[1]
ML_REVISION = "ed3e7c0dfacfdeaf3349dee73edf9e3621217462"
ML_URL = "https://github.com/reticulatedpines/magiclantern_simplified.git"
IMAGE = "glitchlock-ml-builder:bookworm"
DEFAULT_SOURCE_DATE_EPOCH = 1792368000  # 2026-10-19 00:00:00 UTC, overridable release anchor


def run(*args, **kwargs):
    return subprocess.run(*args, check=True, **kwargs)


def normalize_clean_checkout(source):
    """Repair Windows CRLF only when normalized bytes equal the Git blob."""
    index = {}
    for entry in subprocess.check_output(["git", "-C", str(source), "ls-files", "-s", "-z"]).split(b"\0"):
        if entry:
            meta, name = entry.split(b"\t", 1)
            index[name.decode()] = meta.split()[1].decode()
    eol = subprocess.check_output(["git", "-C", str(source), "ls-files", "--eol", "-z", "--", "*.sh"])
    for entry in eol.split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        if b"i/lf" not in meta or b"w/crlf" not in meta:
            continue
        path = source / name.decode()
        data = path.read_bytes().replace(b"\r\n", b"\n")
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != index[name.decode()]:
            raise RuntimeError(f"Refusing to overwrite modified upstream file: {name.decode()}")
        path.write_bytes(data)
    run(["git", "-C", str(source), "config", "core.autocrlf", "false"])


def normalize_module_metadata(path, epoch):
    """Keep upstream metadata generation but remove wall-clock/host variance."""
    text = path.read_text(encoding="utf-8")
    values = {"Build date": datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
              "Build user": "GLITCHLOCK reproducible builder"}
    for label, value in values.items():
        match = re.search(r'static char (__module_string_[a-z]+)_name\s*\[\] MODULE_STRINGS_SECTION = "' + re.escape(label) + r'";', text)
        if not match: raise RuntimeError("Upstream metadata layout changed: " + label)
        pattern = r'(static char ' + re.escape(match[1]) + r'_value\[\] MODULE_STRINGS_SECTION\s*=\s*)[\s\S]*?;'
        text, count = re.subn(pattern, lambda m: m[1] + json.dumps(value) + ";", text, count=1)
        if count != 1: raise RuntimeError("Could not normalize upstream module metadata")
    path.write_text(text, encoding="utf-8", newline="\n")


def artifact_hashes(output, name):
    # Incidental logs/stale outputs must not become release inputs.
    names = (name + ".mo", name + ".dep", name + ".sym", "README.rst", "elf-report.txt", "import-audit.json")
    return {filename: hashlib.sha256((output / filename).read_bytes()).hexdigest() for filename in sorted(names)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild-image", action="store_true")
    parser.add_argument("--module", default="glock", choices=("glock", "slitscan", "mirror", "feedback", "fragment", "diffract"))
    parser.add_argument("--source-date-epoch", type=int, default=int(os.environ.get("SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH)))
    args = parser.parse_args()
    source = ROOT / ".cache/magiclantern"
    if not source.exists():
        run(["git", "-c", "core.autocrlf=false", "clone", "--no-checkout", "--filter=blob:none", ML_URL, str(source)])
        run(["git", "-C", str(source), "config", "core.autocrlf", "false"])
        run(["git", "-C", str(source), "checkout", "--detach", ML_REVISION])
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != ML_REVISION:
        raise RuntimeError("Refusing to build against a different ML revision")
    normalize_clean_checkout(source)
    run(["git", "-C", str(source), "diff", "--quiet", "HEAD", "--"])
    name = args.module
    module = source / "modules" / name
    module.mkdir(exist_ok=True)
    own = ROOT / "modules" / name
    module_sources = sorted(p for p in own.rglob("*") if p.is_file() and "build" not in p.relative_to(own).parts)
    core_sources = [ROOT / "core/glitchlock.c", ROOT / "core/glitchlock.h"] if name == "glock" else [ROOT / "core/glitchlock.h"] + [ROOT / "modules/glock" / n for n in ("gl_format.c", "gl_format.h", "gl_review.c", "gl_review.h", "gl_memory_ml.h")]
    for path in module_sources:
        destination = module / path.relative_to(own)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    (module / "engine").mkdir(exist_ok=True)
    for path in core_sources: shutil.copy2(path, module / "engine" / path.name)
    shared_sources = []
    if name != "glock":
        shared_sources = sorted(p for p in (ROOT / "modules/fx_common").rglob("*") if p.is_file())
        for p in shared_sources:
            dest = module / "shared" / p.relative_to(ROOT / "modules/fx_common")
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, dest)
    version = re.search(r'^:Version:\s*(\S+)\s*$', (own / "README.rst").read_text(), re.MULTILINE)[1]
    define = "GLOCK_VERSION" if name == "glock" else "FX_VERSION"
    if re.search(r'^#define ' + define + r' "([^"]+)"', (own / (name + ".c" if name == "glock" else "effect_config.h")).read_text(), re.MULTILINE)[1] != version:
        raise RuntimeError("Module source and README version disagree")
    found = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0
    if args.rebuild_image or not found:
        run(["docker", "build", "-f", "tools/ml-builder.Dockerfile", "-t", IMAGE, "."], cwd=ROOT)
    mount = ["--mount", f"type=bind,source={ROOT},target=/work"]
    base = ["docker", "run", "--rm", *mount, "-w", "/work/.cache/magiclantern/modules/" + name, IMAGE]
    run(base + ["make", "-B", "build/module_strings.h"])
    normalize_module_metadata(module / "build/module_strings.h", args.source_date_epoch)
    run(base + ["make", "-j2", "FATAL_WARNINGS=y"])
    output = ROOT / ("build/module" if name == "glock" else "build/modules/" + name)
    output.mkdir(parents=True, exist_ok=True)
    for filename in (name + ".mo", name + ".dep", name + ".sym", "README.rst"):
        shutil.copy2(module / "build" / filename, output / filename)
    compiler = subprocess.check_output(base + ["arm-none-eabi-gcc", "--version"], text=True).splitlines()[0]
    image_id = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE], text=True).strip()
    report = subprocess.check_output(base + ["arm-none-eabi-readelf", "-h", "-A", "-r", "build/" + name + ".mo"], text=True)
    (output / "elf-report.txt").write_text(report, encoding="utf-8", newline="\n")
    audit_report = audit(output / (name + ".mo"), ROOT / ".cache/magiclantern.2025-06-20.EOSM.202.zip",
                         ROOT / "targets/EOSM.202/EOSM_202.sym")
    (output / "import-audit.json").write_text(json.dumps(audit_report, indent=2) + "\n", encoding="utf-8", newline="\n")
    if audit_report["missing_imports"]:
        raise RuntimeError("Module has unresolved exact-core imports: " + ", ".join(audit_report["missing_imports"]))
    if audit_report["module_name"] != name: raise RuntimeError("Built module identity mismatch")
    if audit_report["unregistered_property_handlers"]:
        raise RuntimeError("Module has unregistered property handlers: " + ", ".join(p["name"] for p in audit_report["unregistered_property_handlers"]))
    if sorted((output / (name + ".dep")).read_text().splitlines()) != audit_report["imports"]:
        raise RuntimeError("Generated dependency list disagrees with actual ELF imports")
    manifest = {
        "kind": "development-module", "version": version, "module": name + ".mo",
        "target": {"camera": "EOSM", "canon_firmware": "2.0.2", "ml_source": ML_REVISION,
                   "ml_build_date": "2025-06-20"},
        "compiler": compiler, "builder_image": image_id,
        "source_date_epoch": args.source_date_epoch,
        "verification": {"linked": True, "exact_installed_core_imports": True,
                         "defined_property_handlers_registered": True,
                         "camera_loaded": False, "camera_capture_tested": False},
        "imports": (output / (name + ".dep")).read_text().splitlines(),
        "files": artifact_hashes(output, name),
        "source_files": {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in module_sources + core_sources + shared_sources},
    }
    (output / "build.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"Linked module: {output / (name + '.mo')}")
    print(f"Exact installed-core imports: PASS ({len(audit_report['imports'])} symbols). Camera load remains unverified.")


if __name__ == "__main__":
    main()
