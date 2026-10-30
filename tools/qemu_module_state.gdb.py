"""Read-only GDB observer; source after loading the matching ML core ELF."""
import gdb
import json

modules = []
table = gdb.parse_and_eval("module_list")
first, last = table.type.range()
for index in range(first, last + 1):
    entry = table[index]
    name = entry["name"].string()
    if not name:
        continue
    record = {"name": name, "status": entry["status"].string(),
              "valid": int(entry["valid"]), "enabled": int(entry["enabled"]), "error": int(entry["error"])}
    if int(entry["info"]) > 0x1000:
        info = entry["info"].dereference()
        record["info_name"] = info["name"].string()
        record["api"] = [int(info[key]) for key in ("api_magic", "api_major", "api_minor", "api_patch")]
    if int(entry["strings"]) > 0x1000:
        for string_index in range(64):
            pair = entry["strings"][string_index]
            if not int(pair["name"]):
                break
            if pair["name"].string() == "Version":
                record["version"] = pair["value"].string()
                break
    modules.append(record)
print("MIRROR_QEMU_STATE=" + json.dumps({"ml_started": int(gdb.parse_and_eval("ml_started")),
                                       "lv": int(gdb.parse_and_eval("lv")), "modules": modules}, sort_keys=True))
