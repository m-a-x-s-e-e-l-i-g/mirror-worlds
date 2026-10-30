import unittest
from scripts.test_arm_module_binary import check_log


class BinaryModuleLogTest(unittest.TestCase):
    def setUp(self):
        self.profiles = [{"model": "EOSM", "firmware": "2.0.2"}, {"model": "1100D", "firmware": "1.0.5"}]
        self.log = ("BINARY_PROFILE EOSM 2.0.2 8 480 PASS\nBINARY_PROFILE 1100D 1.0.5 8 240 PASS\n"
                    "BINARY_MODULE_RESULT api=8 profiles=2 unsupported=1 sensor_reads=0 PASS\n")

    def test_complete_scope_checks_api_height_and_native_selection(self):
        rows = check_log(self.log, 8, self.profiles)
        self.assertTrue(rows[0]["native_backend_selected"])
        self.assertFalse(rows[1]["native_backend_selected"])
        rows = check_log(self.log.replace(" 8 ", " 7 ").replace("api=8", "api=7"), 7, self.profiles)
        self.assertFalse(any(row["native_backend_selected"] for row in rows))

    def test_missing_duplicate_or_wrong_profile_cannot_pass(self):
        for log in (self.log.replace("BINARY_PROFILE EOSM 2.0.2 8 480 PASS\n", ""),
                    self.log + "BINARY_PROFILE EOSM 2.0.2 8 480 PASS\n",
                    self.log.replace("1100D 1.0.5 8 240", "1100D 1.0.5 8 480"),
                    self.log.replace("EOSM 2.0.2 8", "EOSM 2.0.2 7"),
                    self.log.replace("EOSM 2.0.2", "EOSM 0.0.0")):
            with self.subTest(log=log), self.assertRaises(ValueError):
                check_log(log, 8, self.profiles)

    def test_partial_completion_and_explicit_failure_are_rejected(self):
        for log in (self.log.split("BINARY_MODULE_RESULT")[0], self.log.replace("sensor_reads=0", "sensor_reads=1"),
                    self.log + "BINARY_MODULE_RESULT api=8 profiles=2 unsupported=1 sensor_reads=0 PASS\n",
                    self.log + "BINARY FIXTURE FAIL line 123: corrupted output\n"):
            with self.subTest(log=log), self.assertRaises(ValueError):
                check_log(log, 8, self.profiles)


if __name__ == "__main__":
    unittest.main()
