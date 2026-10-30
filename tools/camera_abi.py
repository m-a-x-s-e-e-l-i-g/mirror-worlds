"""Read the shared struct fields used by Mirror from real ARM ELF DWARF types."""
import json
import subprocess

# Compare field bit offsets, widths and storage sizes, including menu bitfields.
# This deliberately excludes Canon task/DMA structs: native adapters own those.
FIELDS = {
    "vram_info": ("vram", "width", "pitch", "height"),
    "lens_info": ("job_state",),
    "config_var": ("value",),
    "display_filter_buffers": ("src_buf", "dst_buf"),
    "menu_entry": ("name", "priv", "max", "min", "children", "select", "update", "choices", "help", "selected"),
    "menu_display_info": ("value", "help", "warning", "warning_level", "enabled"),
}


def inspect_abi(elf):
    code = ("import gdb,json; wanted=" + repr(FIELDS) + "; "
            "types={name:gdb.lookup_type('struct '+name) for name in wanted}; "
            "result={name:{'size':t.sizeof,'fields':{f.name:[f.bitpos,f.bitsize,f.type.sizeof] "
            "for f in t.fields() if f.name in wanted[name]}} for name,t in types.items()}; "
            "print('MIRROR_ABI='+json.dumps(result,sort_keys=True))")
    result = subprocess.check_output(["gdb-multiarch", "--nx", "--batch", "-ex", "file " + str(elf), "-ex", "python " + code], text=True)
    lines = [line.removeprefix("MIRROR_ABI=") for line in result.splitlines() if line.startswith("MIRROR_ABI=")]
    if len(lines) != 1:
        raise ValueError("Missing GDB structure-layout evidence")
    report = json.loads(lines[0])
    for name, fields in FIELDS.items():
        if set(report[name]["fields"]) != set(fields):
            raise ValueError("Missing ABI field in " + name)
    return report


def compare_abi(module, core):
    differences = []
    for name, fields in FIELDS.items():
        if module[name]["size"] != core[name]["size"]:
            differences.append(name + ".sizeof")
        for field in fields:
            if module[name]["fields"][field] != core[name]["fields"][field]:
                differences.append(name + "." + field)
    return {"result": "layout_mismatch" if differences else "checked_layouts_match",
            "differences": differences, "structs_checked": len(FIELDS),
            "fields_checked": sum(map(len, FIELDS.values())),
            "evidence_limit": "Only the listed shared fields and struct sizes; not a general ABI or runtime validation."}
