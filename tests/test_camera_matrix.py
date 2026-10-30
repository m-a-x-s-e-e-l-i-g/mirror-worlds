import json
from pathlib import Path
import tempfile
import unittest

from tools.camera_matrix import active_defines, attach_arm_mirror_probe, attach_capture_research, attach_core_checks, attach_main_module_research, attach_native_sequence_research, create_matrix, inspect_roms, launcher_models, load_scope, markdown_report, module_profiles

ROOT = Path(__file__).resolve().parents[1]


class CameraMatrixTest(unittest.TestCase):
    def test_native_sequence_is_research_only_and_requires_each_full_frame(self):
        row = {"model": "70D", "liveview_effect_eligible": True,
               "module_profiles": [{"firmware": "1.1.2", "native_raw": False}],
               "raw_capture_in_emulator": "not_verified", "candidate_hardware_test": "not_tested"}
        report = {"models": [row], "counts": {}}
        evidence = {"kind": "research-main-module-native-sequence-verified", "model": "70D", "firmware": "1.1.2",
                    "module_sha256": "research", "normal_module_sha256": "normal", "raw_pixels_checked": 61938432,
                    "raw_pixel_mismatches": 0, "consecutive_shots_in_one_boot_verified": True,
                    "cancellation_before_mutation_verified": True, "off_cleanup_verified": True, "qmp_shutdown_verified": True,
                    "synthetic_preview_injected": True, "synthetic_sensor_input": True, "software_full_press_injected": True,
                    "software_liveview_start_injected": True, "completion_only_preprocessing_model": True,
                    "real_liveview_delivery_verified": False, "native_backend_enabled_in_normal_module": False,
                    "hardware_test": False, "evidence_limit": "Research only", "shots": [
                        {"params": params, "cr2_sha256": str(i), "raw_pixels_checked": 20646144,
                         "raw_pixel_mismatches": 0, "changed_pixels": 9000000, "unchanged_margin_pixels": 684288}
                        for i, params in enumerate(([180, 2, 2, 2], [180, 15, 3, 3], [180, 4, 2, 2]))]}
        attach_native_sequence_research(report, evidence, {"legacy": "other"})
        self.assertNotIn("research_main_module_sequence", row)
        attach_native_sequence_research(report, evidence, {"legacy": "normal"})
        self.assertEqual(report["counts"]["research_main_module_sequence_models_verified"], 1)
        self.assertEqual(row["raw_capture_in_emulator"], "not_verified")
        self.assertEqual(row["candidate_hardware_test"], "not_tested")
        self.assertFalse(row["module_profiles"][0]["native_raw"])
        for key in ("hardware_test", "native_backend_enabled_in_normal_module", "real_liveview_delivery_verified"):
            evidence[key] = True
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "incompatible support"):
                attach_native_sequence_research(report, evidence, {"legacy": "normal"})
            evidence[key] = False
        evidence["shots"][2]["raw_pixel_mismatches"] = 1
        with self.assertRaisesRegex(ValueError, "pixel/lifecycle"):
            attach_native_sequence_research(report, evidence, {"legacy": "normal"})

    def test_research_main_capture_never_promotes_normal_native_support(self):
        row = {"model": "70D", "liveview_effect_eligible": True,
               "module_profiles": [{"firmware": "1.1.2", "native_raw": False}],
               "raw_capture_in_emulator": "not_verified", "candidate_hardware_test": "not_tested"}
        report = {"models": [row], "counts": {}}
        evidence = {"kind": "research-main-module-registered-cr2", "model": "70D", "firmware": "1.1.2",
                    "module_sha256": "research", "normal_module_sha256": "normal", "module_version": "dev",
                    "qemu_revision": "fork", "qemu_sha256": "emulator", "cr2_sha256": "photo",
                    "main_saved_mirrored_cr2_verified": True, "off_cleanup_verified": True,
                    "patched_emulator": True, "completion_only_preprocessing_model": True,
                    "synthetic_preview_injected": True, "synthetic_sensor_input": True, "software_full_press_injected": True,
                    "real_liveview_delivery_verified": False, "hardware_test": False,
                    "native_backend_enabled_in_normal_module": False, "raw_pixels_checked": 20646144,
                    "raw_pixel_mismatches": 0, "changed_pixels": 9356603, "unchanged_margin_pixels": 684288,
                    "params": [180, 2, 2, 2], "observed_latch_to_stage_ms": 244.288, "evidence_limit": "Research only"}
        attach_main_module_research(report, evidence, {"legacy": "different"})
        self.assertNotIn("research_main_module_capture", row)
        attach_main_module_research(report, evidence, {"legacy": "normal"})
        self.assertEqual(report["counts"]["research_main_module_cr2_models_verified"], 1)
        self.assertEqual(row["raw_capture_in_emulator"], "not_verified")
        self.assertEqual(row["candidate_hardware_test"], "not_tested")
        self.assertFalse(row["module_profiles"][0]["native_raw"])
        for key, value in (("hardware_test", True), ("real_liveview_delivery_verified", True),
                           ("native_backend_enabled_in_normal_module", True), ("raw_pixel_mismatches", 1),
                           ("unchanged_margin_pixels", 0), ("module_sha256", "normal")):
            original = evidence[key]
            evidence[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "incompatible support"):
                attach_main_module_research(report, evidence, {"legacy": "normal"})
            evidence[key] = original

    def test_70d_research_build_does_not_promote_normal_native_support(self):
        path = ROOT / "modules/mirror/mirror_camera.c"
        normal = module_profiles(path)
        research = module_profiles(path, research_70d=True)
        self.assertEqual(len(normal), 15)
        self.assertEqual([p["model"] for p in normal if p["native_raw"]], ["EOSM"])
        self.assertEqual({p["model"] for p in research if p["native_raw"]}, {"EOSM", "70D"})
        self.assertEqual([p for p in normal if p["model"] != "70D"],
                         [p for p in research if p["model"] != "70D"])

    def test_only_approved_scope_and_5dc_alias(self):
        scope = load_scope(ROOT / "targets/official-cameras.json")
        self.assertEqual(len(scope["models"]), 21)
        self.assertNotIn("1300D", {m["model"] for m in scope["models"]})
        self.assertEqual(next(m["qemu"] for m in scope["models"] if m["model"] == "5DC"), "5D")
        allowed = {m["model"] for m in scope["models"]}
        self.assertTrue({p["model"] for p in module_profiles(ROOT / "modules/mirror/mirror_camera.c")} <= allowed)

    def test_commented_display_filters_are_not_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "internals.h"
            path.write_text("//~ #define CONFIG_DISPLAY_FILTERS\n/* #define CONFIG_DISPLAY_FILTERS */\n#define CONFIG_LIVEVIEW\n")
            self.assertNotIn("CONFIG_DISPLAY_FILTERS", active_defines(path))

    def test_approved_model_without_source_remains_unresolved(self):
        scope = load_scope(ROOT / "targets/official-cameras.json")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = create_matrix(scope, {}, set(), root, [], root / "roms")
        self.assertEqual(report["counts"]["unresolved_models"], 21)
        self.assertEqual(report["counts"]["excluded_models"], 0)
        self.assertEqual(report["counts"]["emulator_boots_verified"], 0)
        self.assertTrue(all(r["module_loaded_in_emulator"] == "not_verified" for r in report["models"]))
        self.assertIn("Static source/input audit only", markdown_report(report))

    def test_scope_violation_refused(self):
        scope = load_scope(ROOT / "targets/official-cameras.json")
        with self.assertRaisesRegex(ValueError, "outside the approved scope"):
            create_matrix(scope, {}, set(), ROOT, [{"model": "1300D"}], ROOT)

    def test_display_filter_ineligible_profile_refused(self):
        scope = load_scope(ROOT / "targets/official-cameras.json")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            port = root / "platform/500D.111"
            port.mkdir(parents=True)
            (port / "internals.h").write_text("#define CONFIG_LIVEVIEW\n// #define CONFIG_DISPLAY_FILTERS\n")
            (port / "Makefile").write_text("PLATFORM_ARCH = armv5te\n")
            with self.assertRaisesRegex(ValueError, "without ML display-filter support"):
                create_matrix(scope, {}, set(), root, [{"model": "500D"}], root)

    def test_placeholder_files_cannot_make_inputs_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "EOSM/202"
            folder.mkdir(parents=True)
            file = folder / "SFDATA.BIN"
            file.write_bytes(b"EOSM_SFDATA" + bytes(4096 - 11))
            state = inspect_roms(root, "EOSM", "202", [{"name": file.name, "expected_bytes": file.stat().st_size}])
            self.assertTrue(state["files"][0]["size_matches"])
            self.assertTrue(state["files"][0]["placeholder_suspected"])
            self.assertFalse(state["available"])
            file.write_bytes(bytes(range(256)) * 16)
            state = inspect_roms(root, "EOSM", "202", [{"name": file.name, "expected_bytes": 4096}])
            self.assertTrue(state["available"])
            self.assertFalse(state["firmware_identity_verified"])

    def test_source_core_checks_reject_stale_modules_without_claiming_boot(self):
        report = {"ml_source_revision": "pin", "counts": {}, "models": [{"model": "EOSM", "blockers": [],
                  "module_profiles": [{"model": "EOSM", "firmware": "2.0.2"}], "emulator_boot": "not_run"}]}
        evidence = {"revision": "pin", "evidence_limit": "Source core only", "targets": [{
            "target": "EOSM.202", "build_result": "passed", "candidate_audits": {"legacy": {
                "module_sha256": "current", "result": "imports_resolve",
                "checked_struct_layouts": {"result": "checked_layouts_match"}}}}]}
        with self.assertRaisesRegex(ValueError, "Stale core audit"):
            attach_core_checks(report, evidence, {"legacy": "changed"})
        attach_core_checks(report, evidence, {"legacy": "current"})
        self.assertEqual(report["counts"]["source_core_profiles_matching"], 1)
        self.assertEqual(report["models"][0]["emulator_boot"], "not_run")
        evidence["targets"][0]["candidate_audits"]["legacy"]["checked_struct_layouts"]["result"] = "layout_mismatch"
        attach_core_checks(report, evidence, {"legacy": "current"})
        self.assertEqual(report["counts"]["source_core_profiles_matching"], 0)
        self.assertIn("EOSM.202: import_or_field_mismatch", report["models"][0]["blockers"])

    def test_failed_core_is_not_removed_or_counted_as_verified(self):
        report = {"ml_source_revision": "pin", "counts": {}, "models": [{"model": "7D", "blockers": [],
                  "module_profiles": [{"model": "7D", "firmware": "2.0.3"}]}]}
        evidence = {"revision": "pin", "evidence_limit": "Source core only", "targets": [
            {"target": "7D.203", "build_result": "failed"}]}
        attach_core_checks(report, evidence, {"legacy": "current"})
        self.assertEqual(report["counts"]["source_core_profiles_matching"], 0)
        self.assertEqual(report["models"][0]["source_core_checks"][0]["result"], "core_build_failed")

    def test_generated_cr2_does_not_promote_module_capture_or_hardware(self):
        row = {"model": "70D", "liveview_effect_eligible": True,
               "module_profiles": [{"firmware": "1.1.2", "native_raw": False}],
               "raw_capture_in_emulator": "not_verified", "candidate_hardware_test": "not_tested"}
        report = {"models": [row], "counts": {}}
        evidence = {"kind": "experimental-canon-cr2-output", "model": "70D", "firmware": "1.1.2",
                    "module": {"sha256": "current"}, "patched_emulator": True,
                    "completed_canon_cr2_verified": True, "native_mirror_verified": False,
                    "hardware_test": False, "qemu_revision": "separate-fork",
                    "cr2": {"cr2_pixels_equal_sensor_roi": True, "sha256": "photo", "raw_pixels_checked": 20646144}}
        attach_capture_research(report, evidence, {"legacy": "other"})
        self.assertNotIn("experimental_canon_cr2", row)
        attach_capture_research(report, evidence, {"legacy": "current"})
        self.assertEqual(report["counts"]["experimental_generated_cr2_models_verified"], 1)
        self.assertEqual(row["raw_capture_in_emulator"], "not_verified")
        self.assertEqual(row["candidate_hardware_test"], "not_tested")
        self.assertFalse(row["module_profiles"][0]["native_raw"])
        evidence["hardware_test"] = True
        with self.assertRaisesRegex(ValueError, "incompatible claims"):
            attach_capture_research(report, evidence, {"legacy": "current"})
        evidence["hardware_test"] = False
        evidence["firmware"] = "1.1.1"
        with self.assertRaisesRegex(ValueError, "outside the eligible"):
            attach_capture_research(report, evidence, {"legacy": "current"})

    def test_arm_probe_keeps_ordinary_native_backend_unverified(self):
        row = {"model": "70D", "liveview_effect_eligible": True,
               "module_profiles": [{"firmware": "1.1.2", "native_raw": False}],
               "raw_capture_in_emulator": "not_verified", "candidate_hardware_test": "not_tested"}
        report = {"models": [row], "counts": {}}
        evidence = {"kind": "isolated-70d-arm-mirror-probe", "model": "70D", "firmware": "1.1.2",
                    "mirror_module_sha256": "current", "probe_module_sha256": "probe",
                    "isolated_arm_mirror_probe_verified": True, "two_mirrored_shots_in_one_boot": True,
                    "normal_mirror_module_native_backend_tested": False, "hardware_test": False,
                    "validation": {"runs": [{"mode": 2, "independent_expected_pixels_match": True,
                        "raw_pixels_checked": 20646144, "params": [180, 2, 2, 2]},
                        {"mode": 2, "independent_expected_pixels_match": True,
                        "raw_pixels_checked": 20646144, "params": [180, 15, 3, 3]}]}}
        attach_arm_mirror_probe(report, evidence, {"legacy": "stale"})
        self.assertNotIn("experimental_arm_mirror_probe", row)
        attach_arm_mirror_probe(report, evidence, {"legacy": "current"})
        self.assertEqual(report["counts"]["experimental_arm_mirror_probe_models_verified"], 1)
        self.assertEqual(row["raw_capture_in_emulator"], "not_verified")
        self.assertEqual(row["candidate_hardware_test"], "not_tested")
        self.assertFalse(row["module_profiles"][0]["native_raw"])
        original_params = evidence["validation"]["runs"][1]["params"]
        evidence["validation"]["runs"][1]["params"] = evidence["validation"]["runs"][0]["params"]
        with self.assertRaisesRegex(ValueError, "incompatible support"):
            attach_arm_mirror_probe(report, evidence, {"legacy": "current"})
        evidence["validation"]["runs"][1]["params"] = original_params
        evidence["normal_mirror_module_native_backend_tested"] = True
        with self.assertRaisesRegex(ValueError, "incompatible support"):
            attach_arm_mirror_probe(report, evidence, {"legacy": "current"})


if __name__ == "__main__":
    unittest.main()
