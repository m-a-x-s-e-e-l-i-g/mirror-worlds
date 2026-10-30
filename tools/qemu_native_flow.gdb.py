"""Read native-flow state; optionally queue a ticketed request in QEMU only."""
import gdb
import json
import os
from pathlib import Path
import subprocess

debug = Path(os.environ["MIRROR_FLOW_DEBUG"])
symbols = {row.split()[-1]: int(row.split()[0], 16) for row in subprocess.check_output(
    ["arm-none-eabi-nm", "-a", str(debug)], text=True).splitlines()
    if len(row.split()) == 3 and all(c in "0123456789abcdefABCDEF" for c in row.split()[0])}
table = gdb.parse_and_eval("module_list")
found = {}
for index in range(table.type.range()[1] + 1):
    row = table[index]
    name = row["name"].string()
    if name in ("mirror", "mflow"):
        found[name] = row
out = {"ml_started": int(gdb.parse_and_eval("ml_started")), "lv": int(gdb.parse_and_eval("lv")),
       "gui_state": int(gdb.parse_and_eval("gui_state")), "job": int(gdb.parse_and_eval("lens_info.job_state")),
       "modules": {n: {"status": r["status"].string(), "error": int(r["error"])} for n, r in found.items()}}
if "mirror" in found and found["mirror"]["status"].string() == "OK":
    row = found["mirror"]
    text = int(row["info"]["init"]) - symbols["init"]
    bss = int(row["config"][0]["ref"]["value"]) - symbols["mirror_active"]
    gdb.execute("add-symbol-file " + str(debug) + " " + hex(text) + " -s .bss " + hex(bss))
    camera = gdb.parse_and_eval("'fx_camera.c'::camera")
    gate = gdb.parse_and_eval("'mirror_capture_gate.c'::gate")
    trace = gdb.parse_and_eval("'mirror_raw_trace.c'::trace")
    out["preview"] = {k: int(camera["report"][k]) for k in ("running", "frames", "error", "allocated")}
    out["preview"].update({k: int(camera[k]) for k in ("delivery_valid", "canvas_valid")})
    keys = ("phase", "error", "core_error", "latched", "patch_started", "patch_done", "patch_verified", "patch_mismatches",
            "patch_changed", "held_us", "source", "job", "full_ms", "preview_ms", "enter_us", "release_us", "patch_us",
            "sample_mode", "before_count", "after_count", "changed", "overlaps", "sleeps", "cpsr", "lr", "context",
            "dma_before", "dma_after", "dma_address", "dma_pointer")
    out["gate"] = {k: int(gate["r"][k]) for k in keys}
    out["gate"]["installed"] = int(gate["installed"])
    out["gate"]["params"] = [int(gate["r"]["params"]["value"][i]) for i in range(4)]
    out["workspace"] = {"held": int(camera["scratch_held"]), "canvas_bytes": int(camera["canvas_bytes"]),
                        "gate_data": int(gate["scratch"]["data"])}
    layout = gate["patch_map"]
    out["raw_map"] = {"region": [int(layout[k]) for k in ("top", "left", "bottom", "right")],
                      "frame": {k: int(layout["source"][k]) for k in ("width", "height", "pitch", "size", "format")}}
    out["trace"] = {k: int(trace["r"][k]) for k in ("phase", "error", "core_error", "error_pc")}
    out["trace"]["installed"] = int(trace["installed"])
if "mflow" in found and found["mflow"]["status"].string() == "OK":
    row = found["mflow"]
    keys = ("command", "completed", "result", "frames", "ticket", "completed_ticket", "edges", "width", "height")
    out["flow"] = {k: int(row["config"][i]["ref"]["value"].dereference()) for i, k in enumerate(keys)}
    action = int(os.environ.get("MIRROR_FLOW_ACTION", "0"))
    if action:
        reply = gdb.execute("maintenance packet qqemu.sstepbits", to_string=True)
        if not ("ENABLE=" in reply and "NOIRQ=" in reply and "NOTIMER=" in reply):
            raise ValueError("Mailbox writes are allowed only on QEMU")
        ticket = int(os.environ["MIRROR_FLOW_TICKET"])
        if not 1 <= action <= 8 or ticket <= out["flow"]["ticket"] or out["flow"]["command"] or out["flow"]["ticket"] != out["flow"]["completed_ticket"]:
            raise ValueError("Busy or stale native-flow request")
        values = {"ticket": ticket}
        if action == 2:
            values.update(zip(("edges", "width", "height"), map(int, os.environ["MIRROR_FLOW_PARAMS"].split(","))))
        for key, value in values.items():
            address = int(row["config"][keys.index(key)]["ref"]["value"])
            gdb.execute("set {unsigned int}" + hex(address) + " = " + str(value))
        address = int(row["config"][0]["ref"]["value"])
        gdb.execute("set {unsigned int}" + hex(address) + " = " + str(action))
        out["queued"] = {"action": action, "ticket": ticket}
print("MFLOW_STATE=" + json.dumps(out, sort_keys=True))
