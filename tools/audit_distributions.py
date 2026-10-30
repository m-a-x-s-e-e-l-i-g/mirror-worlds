"""Audit cached ML distribution exports and peer API metadata without running them.

Peer metadata is deliberately separate from the strict candidate ELF audit: older
ML modules may omit empty callback/property tables and still be valid peers.
Neither peer API bytes nor resolved names establish core structure layouts.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import struct
import zipfile

from tools.audit_camera_cores import audit_imports
from tools.audit_module import ARCHIVE_SHA256, inspect_module
from tools.camera_matrix import load_scope, module_profiles

ROOT = Path(__file__).resolve().parents[1]
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_MEMBER = 16 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def peer_api(data):
    """Read only the ELF symbol-addressed module-info prefix, with bounds checks."""
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("Peer is not ELF32 little-endian")
    h = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
    if h[1:3] != (1, 40):
        raise ValueError("Peer is not an ARM relocatable object")
    offset, stride, count = h[6], h[11], h[12]
    if stride != 40 or not count or offset + count * stride > len(data):
        raise ValueError("Invalid peer section table")
    sections = [struct.unpack_from("<10I", data, offset + i * stride) for i in range(count)]

    def section(index):
        if not 0 < index < count:
            raise ValueError("Invalid peer section index")
        s = sections[index]
        if s[1] == 8 or s[4] + s[5] > len(data):
            raise ValueError("Peer metadata requires file-backed section bytes")
        return data[s[4]:s[4] + s[5]]

    found = []
    for i, s in enumerate(sections):
        if s[1] != 2:
            continue
        if s[9] != 16 or s[5] % 16 or not 0 < s[6] < count or sections[s[6]][1] != 3:
            raise ValueError("Invalid peer symbol table")
        names, symbols = section(s[6]), section(i)
        for at in range(0, len(symbols), 16):
            name, value, size, info, _, index = struct.unpack_from("<IIIBBH", symbols, at)
            if not name or info >> 4 not in (1, 2):
                continue
            end = names.find(b"\0", name)
            if name >= len(names) or end < 0:
                raise ValueError("Invalid peer symbol name")
            symbol = names[name:end].decode("ascii")
            if not symbol.startswith("__module_info_"):
                continue
            if not re.fullmatch(r"__module_info_[a-z][a-z0-9_]{0,7}", symbol):
                raise ValueError("Invalid peer module name")
            payload = section(index)
            if size < 4 or value + size > len(payload):
                raise ValueError("Peer module info exceeds its section")
            api = list(payload[value:value + 4])
            if api[0] != 0x5A:
                raise ValueError("Invalid peer module magic")
            found.append({"symbol": symbol, "api": api})
    if len(found) != 1:
        raise ValueError("Missing or ambiguous peer module info")
    return found[0]


def symbol_basename(target):
    model, fw = target.split(".")
    # Pinned platform/1100D.105/Makefile sets ML_MODULES_SYM_NAME=t3_105.sym.
    return ("t3" if model == "1100D" else model) + "_" + fw + ".sym"


def audit_archive(module, record, data):
    """Fail closed on malformed inputs; never extract ZIPs or execute core code."""
    if len(data) > MAX_ARCHIVE or digest(data) != record["sha256"]:
        raise ValueError("Archive size limit or SHA-256 mismatch")
    if "size" in record and len(data) != record["size"]:
        raise ValueError("Archive size differs from provenance")
    if record.get("git_blob_sha1"):
        blob = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        if hashlib.sha1(blob).hexdigest() != record["git_blob_sha1"]:
            raise ValueError("Archive Git blob mismatch")
    kind = record["kind"]
    if kind not in ("official-distribution", "community-distribution"):
        raise ValueError("Unknown distribution provenance kind")
    if kind == "official-distribution" and (record["target"] != "EOSM.202" or record["sha256"] != ARCHIVE_SHA256):
        raise ValueError("Official provenance requires an independently pinned archive")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        if len(members) > 4096 or sum(m.file_size for m in members) > MAX_EXPANDED:
            raise ValueError("Archive expanded size limit")
        names = set()
        for m in members:
            p = PurePosixPath(m.filename)
            key = m.filename.casefold()
            if (key in names or p.is_absolute() or ".." in p.parts or "\\" in m.filename
                    or ":" in m.filename or m.file_size > MAX_MEMBER):
                raise ValueError("Duplicate, unsafe or oversized archive member")
            names.add(key)
        bad = archive.testzip()
        if bad is not None:
            raise ValueError("ZIP integrity failed")
        expected = symbol_basename(record["target"])
        tables = [m.filename for m in members if m.filename.lower().endswith(".sym")]
        if tables != ["ML/modules/" + expected]:
            raise ValueError("Archive export table does not match the exact target")
        table = archive.read(tables[0])
        imports = audit_imports(module, table)
        peers = []
        for m in members:
            if not m.filename.lower().endswith(".mo"):
                continue
            raw = archive.read(m)
            peer = {"member": m.filename, "sha256": digest(raw)}
            try:
                peer.update(peer_api(raw))
                peer["result"] = "metadata_read"
            except (ValueError, UnicodeError, struct.error) as error:
                peer.update(result="metadata_unreadable", error=str(error))
            peers.append(peer)
    candidate_api = inspect_module(module)["module_api"]
    observed = sorted({tuple(p["api"][1:3]) for p in peers if "api" in p})
    # The fourth byte is api_patch. The loader gates on major/minor only.
    if any(p["result"] != "metadata_read" for p in peers) or not peers:
        api_result = "incomplete_peer_metadata"
    elif any(p != tuple(candidate_api[1:3]) for p in observed):
        api_result = "peer_api_differs"
    else:
        api_result = "peer_api_metadata_matches"
    result = {"target": record["target"], "kind": kind, "archive_sha256": digest(data),
              "source_url": record["source_url"], "recommended_for_installation": False,
              "symbol_member": tables[0], "imports": imports,
              "peer_api_result": api_result, "observed_peer_api_major_minor": observed,
              "peers": peers, "core_field_layouts": "not_verified_no_dwarf",
              "module_initialization_verified": False, "raw_capture_verified": False,
              "hardware_verified": False}
    return result, table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="Local archive receipt with SHA-256 and provenance")
    parser.add_argument("--module", type=Path, default=ROOT / "build/modules/mirror/mirror.mo")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt_bytes = args.manifest.read_bytes()
    receipt = json.loads(receipt_bytes)
    profiles = module_profiles(ROOT / "modules/mirror/mirror_camera.c")
    scope = load_scope(ROOT / "targets/official-cameras.json")
    models = {m["model"] for m in scope["models"]}
    eligible = {p["model"] + "." + p["firmware"].replace(".", "") for p in profiles if p["model"] in models}
    module = args.module.read_bytes()
    inspect_module(module)
    records = receipt["archives"]
    keys = [(r["target"], r["kind"], r["sha256"]) for r in records]
    if len(keys) != len(set(keys)) or any(r["target"] not in eligible for r in records):
        raise ValueError("Duplicate distribution or target outside eligible scope")
    output = args.output or ROOT / "build/distribution-audit" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    (output / "mirror.mo").write_bytes(module)
    (output / "input-receipt.json").write_bytes(receipt_bytes)
    for source in ("tools/audit_distributions.py", "tools/audit_module.py", "tools/audit_camera_cores.py",
                   "tools/camera_matrix.py", "targets/official-cameras.json", "modules/mirror/mirror_camera.c"):
        dest = output / "sources" / source
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / source).read_bytes())
    results = []
    for index, record in enumerate(records):
        try:
            path = Path(record["local_path"])
            if path.stat().st_size > MAX_ARCHIVE:
                raise ValueError("Archive exceeds size limit")
            result, table = audit_archive(module, record, path.read_bytes())
            snapshot = str(index) + "-" + record["target"] + ".sym"
            (output / snapshot).write_bytes(table)
            result["symbol_snapshot"] = snapshot
            result["audit_result"] = "audited"
        except (ValueError, OSError, KeyError, RuntimeError, zipfile.BadZipFile) as error:
            result = {"target": record["target"], "kind": record["kind"],
                      "audit_result": "input_rejected", "error": str(error)}
        results.append(result)
        print(record["target"], record["kind"], result.get("imports", {}).get("result", result["audit_result"]),
              result.get("imports", {}).get("missing_imports", []))
    missing = Counter(symbol for r in results for symbol in r.get("imports", {}).get("missing_imports", []))
    audited = {r["target"] for r in results if r["audit_result"] == "audited"}
    report = {"kind": "static-distribution-audit", "module_sha256": digest(module), "archives": results,
              "eligible_profiles": sorted(eligible), "profiles_without_audited_archive": sorted(eligible - audited),
              "common_missing_imports": dict(missing),
              "evidence_limit": "Static archive audit only. Peer API metadata does not prove core layouts or loader compatibility. No archive is installed or recommended; no module initialization, LiveView, RAW capture or hardware validation is established.",
              "artifact_files": {p.relative_to(output).as_posix(): digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}}
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Report:", output / "results.json")


if __name__ == "__main__":
    main()
