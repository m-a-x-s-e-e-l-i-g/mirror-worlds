"""Run isolated 70D main-module capture regression in a private QEMU card copy.

This injects synthetic preview frames and software full-press requests. It neither
tests physical keys nor promotes a backend. RAW pixel verification runs separately.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def local(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Research path outside workspace")
    return path


def request_finished(state, action, ticket):
    flow = state.get("flow", {})
    return flow.get("completed") == action and flow.get("completed_ticket") == ticket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mirror-build", type=Path, required=True)
    parser.add_argument("--helper-build", type=Path, required=True)
    parser.add_argument("--qemu-build", type=Path, required=True)
    parser.add_argument("--input-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform == "win32":
        from tools.linux_runtime import LinuxRuntime
        LinuxRuntime(ROOT, "wsl").run("python3", "-B", "-m", "tools.run_native_capture", *sys.argv[1:])
        return
    from tools.run_camera_matrix_linux import qmp
    output = local(args.output)
    if not output.is_relative_to(ROOT / "build/research"):
        parser.error("Output must stay in build/research")
    if output.exists():
        raise FileExistsError(output)
    mirror, helper, emulator = map(local, (args.mirror_build, args.helper_build, args.qemu_build))
    module = json.loads((mirror / "build.json").read_text())
    control = json.loads((helper / "build.json").read_text())
    source = json.loads((emulator / "source.json").read_text())
    bundle = json.loads(local(args.input_receipt).read_text())
    if not (module["research_70d"] and module["target"]["camera"] == "70D" and
            bundle["target"] == "70D.112" and control["mirror_sha256"] == module["files"]["mirror.mo"] and
            source["kind"] == "experimental-completion-only-qemu-source"):
        raise ValueError("Wrong isolated research cohort")
    for base, mapping in ((mirror, module["files"]), (helper, control["files"])):
        for name, expected in mapping.items():
            if digest(base / name) != expected:
                raise ValueError("Changed module/helper build: " + name)
    for record in bundle["artifacts"].values():
        if digest(local(ROOT / record["path"])) != record["sha256"]:
            raise ValueError("Changed coherent core/card input")
    if digest(emulator / "qemu-system-arm") != source["qemu_sha256"]:
        raise ValueError("Changed research emulator")
    output.mkdir(parents=True)
    native_root = Path.home() / ".cache/mirror-worlds"
    native_root.mkdir(parents=True, exist_ok=True)
    native = Path(tempfile.mkdtemp(prefix="native-regression-", dir=native_root))
    roms = native / "roms/70D/112"
    roms.mkdir(parents=True)
    expected_roms = {"ROM0.BIN": "841f20ec42c4f20032d2c472fb44ff0f55f1353691233e6fd18757836d3647bc",
                     "ROM1.BIN": "3fe42299deb577b269b6901f40597a1939ac5876f22c8c3a0b6ee47219fdd42e",
                     "SFDATA.BIN": "6a4a3824cad4661aa4b689b0287e150547816d685ceb94a7f97a4994512b1672"}
    for name, expected in expected_roms.items():
        path = ROOT / ".cache/roms/70D/112" / name
        if digest(path) != expected:
            raise ValueError("Unexpected Canon input")
        shutil.copyfile(path, roms / name)
    for kind in ("sd", "cf"):
        subprocess.run(["cp", "--sparse=always", str(local(ROOT / bundle["artifacts"][kind]["path"])), str(native / (kind + ".raw"))], check=True)
    with (native / "sd.raw").open("rb") as file:
        partition = struct.unpack_from("<I", file.read(512), 454)[0] * 512
    card = str(native / "sd.raw") + "@@" + str(partition)

    def mcopy(src, dest):
        subprocess.run(["mcopy", "-o", "-i", card, str(src), str(dest)], check=True)

    for kind, path in (("autoexec", "::/autoexec.bin"), ("symbols", "::/ML/modules/" + bundle["symbol_name"])):
        mcopy(path, output / (kind + ".from-card"))
        assert digest(output / (kind + ".from-card")) == bundle["artifacts"][kind]["sha256"]
    for pattern in ("::/ML/SETTINGS/*.en", "::/ML/modules/LOADING.LCK", "::/ML/SETTINGS/mirror?.prf"):
        subprocess.run(["mdel", "-i", card, pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for name, build in (("mirror", mirror), ("mflow", helper)):
        shutil.copyfile(build / (name + ".mo"), output / (name + ".mo"))
        mcopy(build / (name + ".mo"), "::/ML/modules/" + name + ".mo")
        mcopy("::/ML/modules/" + name + ".mo", output / (name + ".from-card"))
        assert digest(output / (name + ".from-card")) == digest(build / (name + ".mo"))
        flag = output / (name + ".en")
        flag.write_bytes(b"")
        mcopy(flag, "::/ML/SETTINGS/" + name + ".en")
    shutil.copyfile(local(ROOT / bundle["artifacts"]["core"]["path"]), output / "core.elf")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    sock = native / "qmp.sock"
    command = [str(emulator / "qemu-system-arm"), "-M", "70D,firmware=112;boot=1", "-display", "none",
               "-monitor", "none", "-no-reboot", "-drive", "if=sd,format=raw,file=" + str(native / "sd.raw"),
               "-drive", "if=ide,format=raw,file=" + str(native / "cf.raw"), "-serial", "file:" + str(output / "serial.log"),
               "-qmp", "unix:" + str(sock) + ",server,nowait", "-gdb", "tcp:127.0.0.1:" + str(port),
               "-d", "mpu,guest_errors,debugmsg", "-plugin", str(emulator / "plugins/libmagiclantern.so") + ",arg=debugmsg_addr=0x6904"]
    report = {"kind": "research-main-module-native-sequence", "model": "70D", "firmware": "1.1.2",
              "hardware_test": False, "raw_pixels_verified": False, "synthetic_preview_injected": True,
              "software_full_press_injected": True, "synthetic_sensor_input": True, "patched_emulator": True,
              "software_liveview_start_injected": True,
              "mirror_build": mirror.relative_to(ROOT).as_posix(), "helper_build": helper.relative_to(ROOT).as_posix(),
              "qemu_build": emulator.relative_to(ROOT).as_posix(), "input_receipt": local(args.input_receipt).relative_to(ROOT).as_posix(),
              "shots": [], "command": command, "rom_sha256": expected_roms, "native": str(native), "gdb_port": port}
    report["runner_source_files"] = {}
    for name in ("tools/run_native_capture.py", "tools/qemu_native_flow.gdb.py", "tools/run_camera_matrix_linux.py",
                 "tools/extract_native_capture.py", "tools/linux_runtime.py"):
        snapshot = output / "launch-sources" / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, snapshot)
        report["runner_source_files"][snapshot.relative_to(output).as_posix()] = digest(snapshot)

    def save():
        (output / "run.json").write_text(json.dumps(report, indent=2) + "\n")

    counter = ticket = 0
    log = (output / "qemu.log").open("w")
    process = subprocess.Popen(command, stdout=log, stderr=log, env={**os.environ, "QEMU_EOS_WORKDIR": str(native / "roms"),
        "QEMU_EOS_CAPTURE_TRACE": "2", "QEMU_EOS_FENCING_RESEARCH": "1", "QEMU_EOS_JP57_CAPTURE_DIR": str(output)})
    report["pid"] = process.pid
    save()

    def observe(label, action=0, params=(2, 2, 2)):
        nonlocal counter, ticket
        if process.poll() is not None:
            raise RuntimeError("Owned QEMU exited with " + str(process.returncode))
        if action:
            ticket += 1
        counter += 1
        result = subprocess.run(["gdb-multiarch", "--nx", "--batch", "-ex", "set pagination off", "-ex", "file " + str(output / "core.elf"),
            "-ex", "target remote 127.0.0.1:" + str(port), "-ex", "source " + str(ROOT / "tools/qemu_native_flow.gdb.py"), "-ex", "detach"],
            env={**os.environ, "MIRROR_FLOW_DEBUG": str(mirror / "mirror.debug.o"), "MIRROR_FLOW_ACTION": str(action),
                 "MIRROR_FLOW_TICKET": str(ticket), "MIRROR_FLOW_PARAMS": ",".join(map(str, params))},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
        path = output / (f"{counter:03d}-" + label + ".log")
        path.write_text(result.stdout)
        result.check_returncode()
        lines = re.findall(r"^MFLOW_STATE=(.+)$", result.stdout, re.M)
        if len(lines) != 1:
            raise ValueError("Missing structured native-flow state: " + str(path))
        state = json.loads(lines[0])
        diagnostic = (output / "qemu.log").read_text(errors="replace")
        if re.search(r"ASSERT\s*:|MEMTX invalid|DRYOS PANIC|Illegal inter", diagnostic):
            raise RuntimeError("Canon assert, invalid access or panic; see QEMU log")
        return state, path

    def wait(label, predicate, seconds=45):
        deadline = time.monotonic() + seconds
        last = None
        while time.monotonic() < deadline:
            time.sleep(1)
            state, path = observe(label)
            last = path
            if predicate(state):
                return state, path
        raise TimeoutError("Native observation deadline on the same owned VM: " + str(last))

    def execute(label, action, params=(2, 2, 2)):
        observe(label + "-queued", action, params)
        return wait(label, lambda state: request_finished(state, action, ticket), 60)

    def prepare(label, params):
        # A completed Canon file write does not imply LV has returned. Request
        # LV_START through Canon's property API; this is an explicit software
        # fixture step and never presented as a physical-key or real LV test.
        current, _ = wait(label + "-idle", lambda state: not state["job"] and state["gui_state"] == 0)
        if not current["lv"]:
            execute(label + "-start-lv", 8)
        wait(label + "-lv", lambda state: state["lv"] == 1 and not state["job"] and state["gui_state"] == 0)
        state, frame = execute(label + "-frame", 2, params)
        if state["flow"]["result"] != 1 or not state["preview"]["delivery_valid"]:
            raise RuntimeError("Synthetic preview delivery failed: " + str(frame))
        execute(label + "-arm", 3)
        armed, arm = wait(label + "-armed", lambda state: state["gate"]["phase"] == 2)
        return frame, arm

    try:
        wait("ready", lambda state: state["ml_started"] and all(state.get("modules", {}).get(n, {}).get("status") == "OK" for n in ("mirror", "mflow")))
        execute("raw-quality", 6)
        qmp(sock, {"execute": "send-key", "arguments": {"keys": [{"type": "qcode", "data": "l"}], "hold-time": 100}})
        wait("lv", lambda state: state["lv"] == 1)
        state, path = execute("menu-on", 1)
        if state["flow"]["result"] != 1:
            raise RuntimeError("Menu ON failed")
        # Cancel one latched lease, then recover through the normal OFF/ON API.
        frame, arm = prepare("cancel", (2, 2, 2))
        state, path = execute("cancel", 7)
        if not (state["flow"]["result"] == 1 and state["gate"]["phase"] == 5 and state["gate"]["error"] == 10 and
                not state["gate"]["patch_started"] and not state["workspace"]["held"] and not state["workspace"]["gate_data"]):
            raise RuntimeError("Cancellation did not release its lease before mutation")
        report["cancel_state"] = path.relative_to(output).as_posix()
        execute("cancel-off", 5)
        execute("recover-on", 1)
        for index, params in enumerate(((2, 2, 2), (15, 3, 3), (4, 2, 2))):
            label = "shot-" + str(index + 1)
            frame, arm = prepare(label, params)
            state, release = execute(label + "-release", 4)
            if state["flow"]["result"] != 0:
                raise RuntimeError("Canon Release failed")
            after, completed = wait(label + "-complete", lambda state: state["gate"]["phase"] in (4, 5) and
                state["gate"]["latched"] == 1 and not state["job"] and
                len(re.findall(r"(IMG_[0-9]+\.CR2) write done", (output / "qemu.log").read_text(errors="replace"))) == index + 1)
            if after["gate"]["phase"] != 4 or after["gate"]["params"] != [180, *params] or not after["gate"]["patch_done"]:
                raise RuntimeError("Main native gate failed or used stale controls")
            shot = output / label
            shot.mkdir()
            for original, name in ((frame, "frame-delivered-check.log"), (arm, "capture-armed-check.log"), (completed, "capture-complete-state.log")):
                shutil.copyfile(original, shot / name)
            for name in ("jp57-input.u16", "jp57-output.ljpeg", "jp57-layout.json"):
                shutil.copyfile(output / name, shot / name)
            filenames = re.findall(r"(IMG_[0-9]+\.CR2) write done", (output / "qemu.log").read_text(errors="replace"))
            report["shots"].append({"directory": label, "params": [180, *params], "cr2": filenames[-1],
                                    "job": after["gate"]["job"], "source": after["gate"]["source"],
                                    "held_us": after["gate"]["held_us"], "patch_us": after["gate"]["patch_us"]})
            save()
            print(label + ": main-module completion observed, " + filenames[-1] + ", params=" + str(params), flush=True)
        execute("menu-off", 5)
        state, path = wait("off-cleanup", lambda state: not state["preview"]["allocated"] and not state["preview"]["running"] and
            not state["workspace"]["held"] and not state["workspace"]["canvas_bytes"] and not state["workspace"]["gate_data"])
        report["cleanup_state"] = path.relative_to(output).as_posix()
        report["observations_passed"] = True
    except Exception as exc:
        report["failure"] = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        if process.poll() is None:
            try:
                qmp(sock, {"execute": "quit"})
                process.wait(timeout=5)
                report["shutdown"] = "qmp_quit"
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                report["shutdown"] = "forced_owned_process"
        report["exit_code"] = process.returncode
        log.close()
        save()
    from tools.extract_native_capture import extract
    extract(output)
    print("Native regression observed; RAW pixel validation still required:", output / "run.json")


if __name__ == "__main__":
    main()
