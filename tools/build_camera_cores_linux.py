"""Linux worker for the pinned per-camera core audit; called by audit_camera_cores."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from camera_abi import inspect_abi


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    archive, plan_path, output = map(lambda value: Path(value).resolve(), sys.argv[1:])
    plan = json.loads(plan_path.read_text())
    if digest(archive) != plan["archive_sha256"]:
        raise ValueError("ML source archive checksum mismatch")
    source = Path.home() / ".cache/mirror-worlds" / ("ml-cores-" + plan["archive_sha256"][:16])
    marker = source / ".mirror-source-archive-sha256"
    if not marker.is_file():
        if source.exists():
            raise FileExistsError("Incomplete source staging; inspect it before reuse: " + str(source))
        source.mkdir(parents=True)
        with tarfile.open(archive) as tar:
            # Reject path traversal and links to outside this private staging tree.
            for member in tar.getmembers():
                path = source / member.name
                if not path.resolve().is_relative_to(source.resolve()) or member.issym() or member.islnk():
                    raise ValueError("Unsafe source archive member: " + member.name)
            tar.extractall(source)
        marker.write_text(plan["archive_sha256"])
    elif marker.read_text() != plan["archive_sha256"]:
        raise ValueError("Staged source archive mismatch")
    compiler = subprocess.check_output(["arm-none-eabi-gcc", "--version"], text=True).splitlines()[0]
    report = {"kind": "local-ml-core-builds", "revision": plan["revision"],
              "source_archive_sha256": plan["archive_sha256"], "compiler": compiler,
              "fatal_warnings": False, "canon_firmware_booted": False, "targets": []}
    report["candidate_layouts"] = {}
    previous = json.loads((output / "builds.json").read_text()) if plan.get("reuse_cores") else None
    if previous and (previous["revision"] != plan["revision"] or previous["source_archive_sha256"] != plan["archive_sha256"]):
        raise ValueError("Existing cores have different source provenance")
    for name, candidate in plan["candidates"].items():
        path = output.parents[1] / candidate["path"]
        if digest(path) != candidate["sha256"]:
            raise ValueError("Candidate changed before ABI inspection")
        debug = output.parents[1] / candidate["debug_path"]
        if digest(debug) != candidate["debug_sha256"]:
            raise ValueError("Candidate debug object changed before ABI inspection")
        stripped = output / (name + "-debug-check.mo")
        subprocess.run(["arm-none-eabi-strip", "--strip-debug", "--strip-unneeded", "--discard-all", "--discard-locals",
                        "-o", str(stripped), str(debug)], check=True)
        if digest(stripped) != candidate["sha256"]:
            raise ValueError("Debug types do not describe the supplied module")
        report["candidate_layouts"][name] = inspect_abi(debug)
    for target in plan["targets"]:
        if not target.replace(".", "").isalnum() or target.count(".") != 1:
            raise ValueError("Invalid core target")
        folder = source / "platform" / target
        dest = output / target
        dest.mkdir(parents=True, exist_ok=True)
        if previous:
            matches = [r for r in previous["targets"] if r["target"] == target]
            if len(matches) != 1:
                raise ValueError("Missing or duplicated existing core: " + target)
            record = matches[0].copy()
            if digest(dest / "build.log") != record["log_sha256"]:
                raise ValueError("Existing core build log changed: " + target)
            if record["build_result"] == "passed":
                if digest(dest / "magiclantern.sym") != record["symbol_table_sha256"] or digest(dest / "magiclantern") != record["core_elf_sha256"]:
                    raise ValueError("Existing core artifact changed: " + target)
                record["core_layouts"] = inspect_abi(dest / "magiclantern")
            record["reused_hash_verified_core"] = True
            record.pop("candidate_audits", None)
            report["targets"].append(record)
            print("Reusing verified core result: " + target + " (" + record["build_result"] + ")", flush=True)
            continue
        print("Building core exports: " + target, flush=True)
        command = ["make", "-C", str(folder), "-j4", "FATAL_WARNINGS=n", "build/magiclantern.sym"]
        # Some older in-scope ports retain their supplied platform settings in
        # a separate default file. Read those settings rather than inventing
        # firmware addresses or modifying the pinned source checkout.
        legacy_defaults = folder / "Makefile.platform.default"
        if legacy_defaults.is_file():
            command += ["-f", "Makefile.platform.default", "-f", "Makefile",
                        "FW_VERSION=" + target.split(".")[1], "TOP_DIR=../.."]
        with (dest / "build.log").open("w") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        record = {"target": target, "build_result": "passed" if result.returncode == 0 else "failed",
                  "exit_code": result.returncode, "log_sha256": digest(dest / "build.log"), "command": command,
                  "supplied_legacy_defaults": legacy_defaults.is_file()}
        if result.returncode == 0:
            for name in ("magiclantern.sym", "magiclantern"):
                shutil.copyfile(folder / "build" / name, dest / name)
            record["symbol_table_sha256"] = digest(dest / "magiclantern.sym")
            record["core_elf_sha256"] = digest(dest / "magiclantern")
            record["core_layouts"] = inspect_abi(dest / "magiclantern")
        else:
            print("Core build failed: " + target + " (see build.log)", flush=True)
        report["targets"].append(record)
        (output / "builds.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "builds.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
