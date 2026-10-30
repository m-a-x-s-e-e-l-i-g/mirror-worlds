"""Extract recorded CR2s from an owned, stopped native-regression VM."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def discover_cr2_paths(listing, names):
    paths = {}
    for name in names:
        if not re.fullmatch(r"IMG_[0-9]+\.CR2", name) or name in paths:
            raise ValueError("Invalid or duplicated recorded Canon filename")
        matches = [line.strip() for line in listing.splitlines()
                   if re.fullmatch(r"::/DCIM/[A-Za-z0-9_]+/" + re.escape(name), line.strip())]
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous Canon image folder: " + name)
        paths[name] = matches[0]
    return paths


def extract(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "build/research"):
        raise ValueError("Native research output must stay in build/research")
    report = json.loads((output / "run.json").read_text())
    if report["shutdown"] != "qmp_quit" or report["exit_code"] != 0 or Path("/proc", str(report["pid"])).exists():
        raise ValueError("Extraction requires the owned VM to have stopped normally")
    native = Path(report["native"]).resolve()
    if not native.is_relative_to(Path.home() / ".cache/mirror-worlds") or not native.name.startswith("native-regression-"):
        raise ValueError("Unexpected owned native card directory")
    card = native / "sd.raw"
    with card.open("rb") as file:
        partition = struct.unpack_from("<I", file.read(512), 454)[0] * 512
    image = str(card) + "@@" + str(partition)
    listing = subprocess.check_output(["mdir", "-/", "-b", "-i", image, "::/DCIM"], text=True)
    paths = discover_cr2_paths(listing, [shot["cr2"] for shot in report["shots"]])
    records = []
    for shot in report["shots"]:
        destination = (output / shot["directory"] / shot["cr2"]).resolve()
        if not destination.is_relative_to(output):
            raise ValueError("Recorded shot escapes its research directory")
        if destination.exists():
            raise FileExistsError(destination)
        subprocess.run(["mcopy", "-i", image, paths[shot["cr2"]], str(destination)], check=True)
        records.append({"card_path": paths[shot["cr2"]], "output": destination.relative_to(output).as_posix(),
                        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "bytes": destination.stat().st_size})
    (output / "cr2-directory-listing.txt").write_text(listing)
    report["cr2_extracted_after_shutdown"] = True
    report["extraction_records"] = records
    (output / "run.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Extracted", len(records), "Canon CR2 files after confirmed owned-VM shutdown")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform == "win32":
        from tools.linux_runtime import LinuxRuntime
        LinuxRuntime(ROOT, "wsl").run("python3", "-B", "-m", "tools.extract_native_capture", *sys.argv[1:])
    else:
        extract(args.run)


if __name__ == "__main__":
    main()
