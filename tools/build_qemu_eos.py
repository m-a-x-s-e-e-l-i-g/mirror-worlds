"""Build the pinned ML QEMU fork in Docker or WSL; no Canon ROMs are downloaded."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REVISION = "4b667a1d3c08ab7a55835d15ddbd884fa754946d"
BRANCH = "qemu-eos-v4.2.1"
IMAGE = "mirror-worlds-qemu-eos:bookworm"
VOLUME = "mirror-worlds-qemu-eos-" + REVISION[:12]

def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--runtime", choices=("docker", "wsl"), default="docker")
    parser.add_argument("--distro", default="Ubuntu", help="WSL distribution, when --runtime wsl")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 64:
        parser.error("--jobs must be between 1 and 64")
    source = ROOT / ".cache/qemu-eos"
    if not source.exists():
        run(["git", "-c", "core.autocrlf=false", "clone", "--depth", "1", "--single-branch",
             "--branch", BRANCH, "https://github.com/reticulatedpines/qemu-eos.git", str(source)])
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if head != REVISION:
        raise RuntimeError(f"Expected QEMU {REVISION}, found {head}")
    run(["git", "-C", str(source), "diff", "--quiet", "HEAD", "--"])
    output = ROOT / "build/qemu-eos"
    output.mkdir(parents=True, exist_ok=True)
    if args.runtime == "wsl":
        prefix = ["wsl", "--distribution", args.distro, "--exec"]
        linux_root = subprocess.check_output(prefix + ["wslpath", "-a", str(ROOT)], text=True).strip()
        linux_cache = subprocess.check_output(prefix + ["python3", "-c",
            "from pathlib import Path; print(Path.home()/'.cache/mirror-worlds/qemu-eos-" + REVISION[:12] + "')"], text=True).strip()
        run(prefix + ["sh", linux_root + "/tools/build_qemu_linux.sh", linux_root + "/.cache/qemu-eos",
                      linux_root + "/build/qemu-eos", linux_cache, str(args.jobs)])
    else:
        build_docker(source, args.jobs)
    manifest = {"kind": "qemu-eos-build", "revision": head, "branch": BRANCH,
                "runtime": args.runtime, "docker_image": IMAGE if args.runtime == "docker" else None,
                "roms_included": False,
                "files": {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                          for name in ("qemu-system-arm", "plugins/libmagiclantern.so")}}
    (output / "build.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Built pinned QEMU-EOS and ML tracing plugin: " + str(output))


def build_docker(source, jobs):
    run(["docker", "build", "-f", str(ROOT / "tools/qemu-eos.Dockerfile"), "-t", IMAGE, str(ROOT / "tools")])
    run(["docker", "volume", "create", VOLUME], stdout=subprocess.DEVNULL)
    command = ["docker", "run", "--rm",
               "--mount", f"type=bind,source={ROOT},target=/work",
               "--mount", f"type=volume,source={VOLUME},target=/qemu-build",
               "-w", "/qemu-build", IMAGE]
    run(command + ["sh", "/work/tools/build_qemu_linux.sh", "/work/.cache/qemu-eos",
                   "/work/build/qemu-eos", "/qemu-build", str(jobs)])

if __name__ == "__main__":
    main()
