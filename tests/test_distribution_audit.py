import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.audit_distributions import audit_archive, peer_api, symbol_basename
from tools.camera_matrix import attach_distribution_checks, load_distribution_evidence


def elf_peer(api=b"\x5a\x08\x00\x00", *, value=12, symbol_size=20):
    """Old-style peer: no empty handler tables; info is not at section offset 0."""
    names = b"\0__module_info_fixture\0"
    symbols = bytes(16) + struct.pack("<IIIBBH", 1, value, symbol_size, 17, 0, 3)
    payload = bytes(value) + api + bytes(16)
    offset = 52 + 4 * 40
    sections = [bytes(40)]
    for kind, raw, link, stride in ((3, names, 0, 0), (2, symbols, 1, 16), (1, payload, 0, 0)):
        sections.append(struct.pack("<10I", 0, kind, 0, 0, offset, len(raw), link, 0, 4, stride))
        offset += len(raw)
    h = struct.pack("<16sHHIIIIIHHHHHH", b"\x7fELF\x01\x01\x01" + bytes(9),
                    1, 40, 1, 0, 0, 52, 0x5000000, 52, 0, 0, 40, 4, 0)
    return h + b"".join(sections) + names + symbols + payload


def distribution(target="7D.203", *, table=b"1000 first\n", peer=None, extra=()):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("ML/modules/" + symbol_basename(target), table)
        z.writestr("ML/modules/fixture.mo", peer if peer is not None else elf_peer())
        for name, data in extra:
            z.writestr(name, data)
    data = buffer.getvalue()
    record = {"target": target, "kind": "community-distribution", "source_url": "https://example.invalid/test.zip",
              "sha256": hashlib.sha256(data).hexdigest()}
    return record, data


class DistributionAuditTest(unittest.TestCase):
    def audit(self, record, data):
        with patch("tools.audit_distributions.inspect_module", return_value={"module_api": [90, 8, 0, 0]}), \
             patch("tools.audit_camera_cores.inspect_module", return_value={"imports": ["first", "missing"]}):
            return audit_archive(b"candidate", record, data)[0]

    def test_metadata_reads_symbol_offset_without_requiring_handler_tables(self):
        self.assertEqual(peer_api(elf_peer())["api"], [90, 8, 0, 0])

    def test_bad_metadata_does_not_read_other_section_or_truncated_symbol(self):
        for raw in (b"ELF", elf_peer(api=b"\0\x08\0\0"), elf_peer(symbol_size=21), elf_peer()[:-1]):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                peer_api(raw)

    def test_missing_imports_and_api_differences_are_separate_from_runtime(self):
        record, raw = distribution(peer=elf_peer(api=b"\x5a\x07\0\0"))
        report = self.audit(record, raw)
        self.assertEqual(report["imports"]["missing_imports"], ["missing"])
        self.assertEqual(report["peer_api_result"], "peer_api_differs")
        self.assertFalse(report["module_initialization_verified"])
        self.assertFalse(report["raw_capture_verified"])
        self.assertFalse(report["hardware_verified"])

    def test_unreadable_peer_is_not_an_api_mismatch(self):
        record, raw = distribution(peer=b"malformed")
        report = self.audit(record, raw)
        self.assertEqual(report["peer_api_result"], "incomplete_peer_metadata")
        self.assertEqual(report["observed_peer_api_major_minor"], [])

    def test_peer_patch_byte_is_preserved_but_does_not_change_major_minor_comparison(self):
        record, raw = distribution(peer=elf_peer(api=b"\x5a\x08\0\x03"))
        report = self.audit(record, raw)
        self.assertEqual(report["peers"][0]["api"], [90, 8, 0, 3])
        self.assertEqual(report["peer_api_result"], "peer_api_metadata_matches")

    def test_matching_imports_and_metadata_do_not_verify_structs(self):
        record, raw = distribution(table=b"1000 first\n2000 missing\n")
        report = self.audit(record, raw)
        self.assertEqual(report["imports"]["result"], "imports_resolve")
        self.assertEqual(report["peer_api_result"], "peer_api_metadata_matches")
        self.assertEqual(report["core_field_layouts"], "not_verified_no_dwarf")
        self.assertFalse(report["recommended_for_installation"])

    def test_wrong_target_and_duplicate_case_paths_rejected(self):
        record, raw = distribution()
        record["target"] = "70D.112"
        with self.assertRaisesRegex(ValueError, "exact target"):
            self.audit(record, raw)
        record, raw = distribution(extra=(("ml/MODULES/7d_203.sym", b"1000 first\n"),))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.audit(record, raw)

    def test_hash_and_provenance_cannot_be_promoted(self):
        record, raw = distribution()
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.audit(record, raw + b"changed")
        record["kind"] = "official-distribution"
        with self.assertRaisesRegex(ValueError, "independently pinned"):
            self.audit(record, raw)
        record["kind"] = "community-distribution"
        record["git_blob_sha1"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "Git blob"):
            self.audit(record, raw)

    def test_t3_alias_is_exact_firmware_specific(self):
        record, raw = distribution("1100D.105")
        report = self.audit(record, raw)
        self.assertEqual(report["symbol_member"], "ML/modules/t3_105.sym")
        record["target"] = "1100D.106"
        with self.assertRaisesRegex(ValueError, "exact target"):
            self.audit(record, raw)

    def test_matrix_keeps_static_mismatch_separate_and_rejects_stale_scope_and_claims(self):
        record, raw = distribution(peer=elf_peer(api=b"\x5a\x07\0\0"))
        archive = self.audit(record, raw)
        archive["audit_result"] = "audited"
        evidence = {"kind": "static-distribution-audit", "module_sha256": archive["imports"]["module_sha256"],
                    "eligible_profiles": ["7D.203"], "archives": [archive], "evidence_limit": "Static only"}
        row = {"model": "7D", "module_profiles": [{"model": "7D", "firmware": "2.0.3"}],
               "blockers": [], "module_loaded_in_emulator": "not_verified", "candidate_hardware_test": "not_tested"}
        report = {"models": [row], "counts": {}}
        hashes = {"legacy": evidence["module_sha256"]}
        attach_distribution_checks(report, evidence, hashes)
        self.assertEqual(report["counts"]["community-distribution_archives_matching"], 0)
        self.assertEqual(row["distribution_checks"][0]["result"], "import_or_peer_api_mismatch")
        self.assertEqual(row["module_loaded_in_emulator"], "not_verified")
        self.assertEqual(row["candidate_hardware_test"], "not_tested")
        with self.assertRaisesRegex(ValueError, "Stale"):
            attach_distribution_checks(report, evidence, {"legacy": "changed"})
        evidence["eligible_profiles"] = ["70D.112"]
        with self.assertRaisesRegex(ValueError, "scope"):
            attach_distribution_checks(report, evidence, hashes)
        evidence["eligible_profiles"] = ["7D.203"]
        archive["hardware_verified"] = True
        with self.assertRaisesRegex(ValueError, "claims"):
            attach_distribution_checks(report, evidence, hashes)

    def test_snapshot_changes_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {"mirror.mo": b"candidate", "input-receipt.json": b"{}", "7D.sym": b"1000 first\n"}
            for name, data in files.items():
                (root / name).write_bytes(data)
            hashes = {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}
            evidence = {"module_sha256": hashes["mirror.mo"], "artifact_files": hashes, "archives": [
                {"audit_result": "audited", "symbol_snapshot": "7D.sym", "imports": {"symbol_table_sha256": hashes["7D.sym"]}}]}
            path = root / "results.json"
            path.write_text(json.dumps(evidence))
            load_distribution_evidence(path)
            (root / "7D.sym").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "Changed distribution"):
                load_distribution_evidence(path)
            hashes.pop("7D.sym")
            hashes["../escape"] = "0" * 64
            path.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, "Changed distribution"):
                load_distribution_evidence(path)


if __name__ == "__main__":
    unittest.main()
