import copy
import unittest
from tools.camera_matrix import attach_arm_binary_fixtures


class BinaryMatrixTest(unittest.TestCase):
    def setUp(self):
        self.report = {"counts": {}, "models": [{"model": "EOSM", "module_profiles": [{"firmware": "2.0.2", "native_raw": True}],
                       "emulator_boot": "not_run", "module_loaded_in_emulator": "not_verified", "candidate_hardware_test": "not_tested"}]}
        self.observation = {"kind": "synthetic-arm-module-binaries", "canon_firmware_booted": False,
            "ml_loader_tested": False, "installed_core_layout_verified": False, "native_capture_verified": False,
            "hardware_tested": False, "module_source_recompiled": False, "deliberate_corruption_rejected": True,
            "profiles": [{"model": "EOSM", "firmware": "2.0.2"}], "profile_runs_verified": 4, "evidence_limit": "Synthetic SDK only",
            "variants": [{"api_major": api, "module_sha256": "normal" if api == 8 else "preview", "preview_only": api == 7,
                "cpus": [{"cpu": cpu, "unsupported_firmware_refused": True, "preview_source_and_destination_checked": True,
                    "off_on_and_cleanup_verified": True, "initial_review_seed_verified": True, "review_invalidates_delivery": True,
                    "forbidden_sensor_reads": 0, "profiles": [{"model": "EOSM", "firmware": "2.0.2", "height": 480,
                    "passed": True, "native_backend_selected": api == 8}]} for cpu in ("arm946-eos", "arm946-eos5")]} for api in (8, 7)]}

    def test_never_promotes_canon_or_hardware_status(self):
        attach_arm_binary_fixtures(self.report, self.observation, {"normal": "different"})
        self.assertNotIn("synthetic_arm_module_binary", self.report["models"][0])
        attach_arm_binary_fixtures(self.report, self.observation, {"normal": "normal"})
        row = self.report["models"][0]
        self.assertEqual(len(row["synthetic_arm_module_binary"]), 4)
        self.assertEqual(row["emulator_boot"], "not_run")
        self.assertEqual(row["module_loaded_in_emulator"], "not_verified")
        self.assertEqual(row["candidate_hardware_test"], "not_tested")

    def test_claims_and_missing_cpu_rejected_before_attaching(self):
        for key in ("canon_firmware_booted", "ml_loader_tested", "installed_core_layout_verified", "native_capture_verified",
                    "hardware_tested", "module_source_recompiled"):
            observation = copy.deepcopy(self.observation)
            observation[key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                attach_arm_binary_fixtures(self.report, observation, {"normal": "normal"})
        self.observation["variants"][1]["cpus"].pop()
        with self.assertRaises(ValueError):
            attach_arm_binary_fixtures(self.report, self.observation, {"normal": "normal"})
        self.assertNotIn("synthetic_arm_module_binary", self.report["models"][0])

    def test_api7_cannot_claim_a_native_backend(self):
        self.observation["variants"][1]["cpus"][0]["profiles"][0]["native_backend_selected"] = True
        with self.assertRaises(ValueError):
            attach_arm_binary_fixtures(self.report, self.observation, {"normal": "normal"})


if __name__ == "__main__":
    unittest.main()
