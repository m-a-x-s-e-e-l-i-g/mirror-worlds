import json
import unittest

from tools.analyze_qemu_boot import analyze


class QemuBootObservationTest(unittest.TestCase):
    def setUp(self):
        self.serial = "K325 ICU Firmware Version 1.1.2 (8.1.6)\n[STARTUP] startupInitializeComplete\n"
        self.module = {"name": "mirror", "info_name": "mirror", "api": [90, 8, 0, 0], "status": "OK",
                       "valid": 1, "enabled": 1, "error": 0}

    def state(self, modules, ml_started=1):
        return "MIRROR_QEMU_STATE=" + json.dumps({"ml_started": ml_started, "lv": 0, "modules": modules})

    def test_boot_or_filename_alone_does_not_verify_module(self):
        for state in (self.state([]), self.state([{"**": "not a module", "name": "mirror", "status": "OK", "valid": 0, "enabled": 0, "error": 0}]), self.state([self.module], 0)):
            self.assertFalse(analyze(self.serial, state, "1.1.2", "K325")["module_initialization_observed"])

    def test_failed_init_is_not_accepted(self):
        self.module["error"] = 1
        result=analyze(self.serial, self.state([self.module]), "1.1.2", "K325")
        self.assertFalse(result["module_initialization_observed"])
        self.assertTrue(result["module_initialization_failed_observed"])
        self.assertEqual(result["module_initialization_state"], "failed")

    def test_empty_or_in_progress_module_list_is_pending_not_a_failed_initialization(self):
        self.module["status"] = "Loading"
        for modules in ([],[self.module]):
            result=analyze(self.serial,self.state(modules),"1.1.2","K325")
            self.assertFalse(result["module_initialization_observed"])
            self.assertFalse(result["module_initialization_failed_observed"])
            self.assertEqual(result["module_initialization_state"], "pending")

    def test_successful_init_never_implies_render_capture_or_hardware(self):
        result = analyze(self.serial, self.state([self.module]), "1.1.2", "K325")
        self.assertTrue(result["module_initialization_observed"])
        self.assertFalse(result["preview_render_verified"])
        self.assertFalse(result["native_raw_capture_verified"])
        self.assertFalse(result["hardware_tested"])

    def test_wrong_firmware_or_duplicate_observation_is_rejected(self):
        self.assertFalse(analyze(self.serial, self.state([self.module]), "2.0.2", "K325")["ml_startup_observed"])
        with self.assertRaises(ValueError):
            analyze(self.serial, self.state([self.module]) + "\n" + self.state([self.module]), "1.1.2", "K325")


if __name__ == "__main__":
    unittest.main()
