import unittest
from scripts.test_main_capture_refusal import check_expired_latch


class MainCaptureRefusalTest(unittest.TestCase):
    def gate(self):
        return {"phase": 5, "error": 7, "latched": 1, "installed": 1, "patch_started": 0, "patch_done": 0,
                "patch_verified": 0, "patch_mismatches": 0, "patch_changed": 0, "held_us": 0,
                "enter_us": 106894080, "full_ms": 96898}

    def test_only_a_latched_expired_request_is_this_negative_fixture(self):
        self.assertAlmostEqual(check_expired_latch(self.gate()), 9996.08)
        for key,value in (("latched",0),("error",6),("phase",4),("installed",0)):
            gate=self.gate();gate[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):check_expired_latch(gate)

    def test_pixel_processing_or_an_unexpired_latch_cannot_be_reported_as_safe_refusal(self):
        for key in ("patch_started","patch_done","patch_verified","patch_changed","held_us"):
            gate=self.gate();gate[key]=1
            with self.subTest(key=key),self.assertRaises(ValueError):check_expired_latch(gate)
        gate=self.gate();gate["full_ms"]=106000
        with self.assertRaises(ValueError):check_expired_latch(gate)


if __name__ == "__main__":unittest.main()
