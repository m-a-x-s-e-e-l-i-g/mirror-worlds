import copy
import unittest
from unittest.mock import patch

from tools.audit_camera_cores import audit_imports, parse_exports
from tools.camera_abi import FIELDS, compare_abi


class CameraCoreAuditTest(unittest.TestCase):
    def test_unresolved_core_import_is_not_a_pass(self):
        with patch("tools.audit_camera_cores.inspect_module", return_value={"imports": ["first", "missing"]}):
            report = audit_imports(b"candidate", b"00001000 first\n")
        self.assertEqual(report["missing_imports"], ["missing"])
        self.assertEqual(report["result"], "unresolved_imports")
        self.assertFalse(report["module_load_verified"])

    def test_resolved_names_do_not_claim_runtime_validation(self):
        with patch("tools.audit_camera_cores.inspect_module", return_value={"imports": ["first"]}):
            report = audit_imports(b"candidate", b"00001000 first\n")
        self.assertEqual(report["result"], "imports_resolve")
        self.assertFalse(report["module_load_verified"])
        self.assertFalse(report["native_capture_verified"])

    def test_malformed_and_duplicate_exports_rejected(self):
        for table in (b"not an export\n", b"garbage symbol\n", b"1000 symbol\n2000 symbol\n"):
            with self.subTest(table=table), self.assertRaises(ValueError):
                parse_exports(table)

    def test_shifted_field_and_bitfield_are_reported(self):
        module = {name: {"size": 100, "fields": {field: [index * 32, 0, 4] for index, field in enumerate(fields)}}
                  for name, fields in FIELDS.items()}
        core = copy.deepcopy(module)
        self.assertEqual(compare_abi(module, core)["result"], "checked_layouts_match")
        core["lens_info"]["fields"]["job_state"][0] += 32
        core["menu_entry"]["fields"]["selected"][1] = 1
        core["vram_info"]["size"] += 4
        result = compare_abi(module, core)
        self.assertEqual(result["result"], "layout_mismatch")
        self.assertEqual(set(result["differences"]), {"lens_info.job_state", "menu_entry.selected", "vram_info.sizeof"})


if __name__ == "__main__":
    unittest.main()
