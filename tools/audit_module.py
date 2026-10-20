"""Check real ELF/module metadata and imports against the hash-verified ML ZIP."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA256 = "152f2ab46b83f45b978bcb704bda976849aa9d06b08fb70448f69be3ebfc44fb"
SYMBOL_MEMBER = "ML/modules/EOSM_202.sym"
SYMBOL_SHA256 = "d9ac74b62303e149ccf9b636e9dfd5fb24bc26506660b4b0638acbb51715fb88"


def inspect_module(data, module_name=None):
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("Module must be ELF32 little-endian")
    header = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
    if header[1] != 1 or header[2] != 40:
        raise ValueError("Module must be a relocatable ARM object")
    if header[7] >> 24 != 5 or header[7] & 0x400:
        raise ValueError("Expected ARM EABI5 without hard-float ABI")
    shoff, shsize, shnum, shstrings = header[6], header[11], header[12], header[13]
    if shsize != 40 or not 0 < shstrings < shnum or shoff + shnum * shsize > len(data):
        raise ValueError("Invalid ELF section table")
    sections = [struct.unpack_from("<10I", data, shoff + i * shsize) for i in range(shnum)]

    def section_bytes(index):
        s = sections[index]
        if s[4] + s[5] > len(data): raise ValueError("ELF section exceeds file")
        return data[s[4]:s[4] + s[5]]

    def string(buf, offset):
        end = buf.find(b"\0", offset)
        if offset >= len(buf) or end < 0: raise ValueError("Invalid ELF string")
        return buf[offset:end].decode("ascii")

    names = section_bytes(shstrings)
    section_names = {string(names, s[0]): i for i, s in enumerate(sections)}
    imports, definitions = set(), {}
    for i, s in enumerate(sections):
        if s[1] != 2: continue
        if s[9] != 16 or s[5] % 16 or s[6] >= shnum: raise ValueError("Invalid symbol table")
        strings = section_bytes(s[6]); symbols = section_bytes(i)
        for offset in range(0, len(symbols), 16):
            name, value, size, info, other, section = struct.unpack_from("<IIIBBH", symbols, offset)
            if not name or info >> 4 not in (1, 2): continue
            name = string(strings, name)
            if section == 0: imports.add(name)
            else: definitions[name] = (section, value, size)
    if module_name is None:
        candidates = [n.removeprefix("__module_info_") for n in definitions if n.startswith("__module_info_")]
        if len(candidates) != 1: raise ValueError("Missing or ambiguous ML module metadata")
        module_name = candidates[0]
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,7}", module_name): raise ValueError("Invalid module name")
    required = tuple(p + module_name for p in ("__module_info_", "__module_cbr_", "__module_prophandlers_", "__module_strings_"))
    if any(name not in definitions for name in required): raise ValueError("Missing ML module metadata")
    section, offset, size = definitions["__module_info_" + module_name]
    info = section_bytes(section)[offset:offset + size]
    if len(info) < 4 or info[:3] != bytes((0x5A, 8, 0)):
        raise ValueError("Unexpected Magic Lantern module API")
    relocations = set()
    pointers = {}
    for i, s in enumerate(sections):
        if s[1] != 9: continue
        if s[5] % 8 or s[6] >= shnum or s[7] >= shnum or sections[s[6]][1] != 2:
            raise ValueError("Malformed ARM relocation section")
        raw = section_bytes(i)
        symbols = section_bytes(s[6])
        for offset in range(0, len(raw), 8):
            location, info_word = struct.unpack_from("<II", raw, offset)
            kind, symbol = info_word & 255, info_word >> 8
            # The pinned TinyCC ARM loader implements these emitted types.
            # Keep external calls as ABS32 long calls: no runtime branch-range
            # or veneer assumption for core/ROM addresses far from module RAM.
            if kind not in (2, 28, 29): raise ValueError("Unsupported ARM relocation type")
            if location + 4 > sections[s[7]][5] or (symbol + 1) * 16 > len(symbols):
                raise ValueError("Malformed ARM relocation target")
            if kind == 2:
                key = (s[7], location)
                if key in pointers: raise ValueError("Duplicate ARM pointer relocation")
                _, value, _, _, _, target = struct.unpack_from("<IIIBBH", symbols, symbol * 16)
                addend = struct.unpack_from("<I", section_bytes(s[7]), location)[0]
                pointers[key] = (target, value + addend)
            if kind in (28, 29):
                _, value, _, _, _, defined_section = struct.unpack_from("<IIIBBH", symbols, symbol * 16)
                if defined_section != s[7] or not defined_section:
                    raise ValueError("Direct ARM branch must stay within its module section")
                instruction = struct.unpack_from("<I", section_bytes(s[7]), location)[0]
                addend = instruction & 0xFFFFFF
                if addend & 0x800000: addend -= 0x1000000
                distance = (addend << 2) + value - location
                if distance & 3 or not -(1 << 25) <= distance < (1 << 25):
                    raise ValueError("Direct ARM branch exceeds loader range")
            relocations.add(kind)
    if not relocations: raise ValueError("Missing ARM relocations")

    def pointer(section, offset):
        target, location = pointers.get((section, offset), (0, 0))
        if not 0 < target < shnum or sections[target][1] != 1 or location >= sections[target][5]:
            raise ValueError("Invalid property metadata pointer")
        return target, location

    blocks = {}
    for name, (section, offset, size) in definitions.items():
        if not name.startswith("__module_prophandler_" + module_name + "_") or not name.endswith("_block"): continue
        if size != 16 or offset + size > sections[section][5]: raise ValueError("Invalid property handler block")
        name_section, name_offset = pointer(section, offset)
        label = string(section_bytes(name_section), name_offset)
        handler_section, _ = pointer(section, offset + 4)
        if not sections[handler_section][2] & 4: raise ValueError("Property handler must point to executable code")
        property_id, length = struct.unpack_from("<II", section_bytes(section), offset + 8)
        blocks[(section, offset)] = {"name": label, "property": property_id, "length": length}
    section, offset, size = definitions["__module_prophandlers_" + module_name]
    if size < 4 or size % 4 or offset + size > sections[section][5]: raise ValueError("Invalid property registration table")
    registered = []
    ids = set()
    addresses = set()
    for entry in range(offset, offset + size, 4):
        raw_pointer = struct.unpack_from("<I", section_bytes(section), entry)[0]
        if (section, entry) not in pointers and raw_pointer == 0:
            if entry != offset + size - 4: raise ValueError("Premature property table terminator")
            break
        if entry == offset + size - 4: raise ValueError("Missing property table terminator")
        address = pointer(section, entry)
        if address not in blocks: raise ValueError("Property table must point to a handler block")
        block = blocks[address]
        if block["property"] in ids: raise ValueError("Duplicate property handler registration")
        ids.add(block["property"]); addresses.add(address); registered.append(block)
    unregistered = [block for address, block in blocks.items() if address not in addresses]
    return {"format": "ELF32-ARM-REL", "module_name": module_name, "defined_symbols": sorted(definitions), "module_api": list(info[:4]),
            "imports": sorted(imports), "metadata": list(required),
            "property_handlers": sorted(registered, key=lambda b: b["property"]),
            "unregistered_property_handlers": sorted(unregistered, key=lambda b: b["property"]),
            "sections": sorted(section_names), "flags": header[7], "relocation_types": sorted(relocations)}


def audit(module, archive=None, symbols=None):
    archive_verified_now = archive is not None and archive.exists()
    if archive_verified_now:
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != ARCHIVE_SHA256: raise ValueError("Installed ML archive checksum does not match the specified build")
        with zipfile.ZipFile(archive) as z:
            table = z.read(SYMBOL_MEMBER)
    else:
        if symbols is None: raise ValueError("Provide the verified archive or its pinned symbol table")
        table = symbols.read_bytes()
    if hashlib.sha256(table).hexdigest() != SYMBOL_SHA256:
        raise ValueError("Target symbol table checksum mismatch")
    exports = {}
    for line in table.decode("ascii").splitlines():
        parts = line.split()
        if len(parts) == 2: exports[parts[1]] = int(parts[0], 16)
    report = inspect_module(module.read_bytes())
    report.update({"module_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
                   "archive_sha256": ARCHIVE_SHA256, "archive_verified_now": archive_verified_now,
                   "symbol_member": SYMBOL_MEMBER,
                   "symbol_table_sha256": hashlib.sha256(table).hexdigest(),
                   "resolved_imports": {name: f"0x{exports[name]:08x}" for name in report["imports"] if name in exports},
                   "missing_imports": sorted(set(report["imports"]) - exports.keys()),
                   "camera_load_verified": False})
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", type=Path, default=ROOT / "build/module/glock.mo")
    parser.add_argument("--archive", type=Path, default=ROOT / ".cache/magiclantern.2025-06-20.EOSM.202.zip")
    parser.add_argument("--symbols", type=Path, default=ROOT / "targets/EOSM.202/EOSM_202.sym")
    parser.add_argument("--output", type=Path, default=ROOT / "build/module/import-audit.json")
    args = parser.parse_args()
    report = audit(args.module, args.archive, args.symbols)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    if report["missing_imports"]:
        raise SystemExit("Unresolved target imports: " + ", ".join(report["missing_imports"]))
    if report["unregistered_property_handlers"]:
        raise SystemExit("Defined but unregistered property handlers: " + ", ".join(p["name"] for p in report["unregistered_property_handlers"]))
    print(f"ELF/module ABI and {len(report['imports'])} exact-core imports: PASS")
    print("The actual EOS M module load remains unverified.")


if __name__ == "__main__":
    main()
