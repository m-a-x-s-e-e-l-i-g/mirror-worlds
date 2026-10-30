import unittest
from tools.run_native_capture import request_finished
from tools.extract_native_capture import discover_cr2_paths


class NativeSequenceTest(unittest.TestCase):
    def test_extracts_the_observed_folder_and_rejects_ambiguous_or_invalid_paths(self):
        listing = "::/DCIM/100EOS5D/\n::/DCIM/100EOS5D/IMG_0065.CR2\n::/DCIM/EOSMISC/M2100.CTG\n"
        self.assertEqual(discover_cr2_paths(listing, ["IMG_0065.CR2"]), {"IMG_0065.CR2": "::/DCIM/100EOS5D/IMG_0065.CR2"})
        for text, names in ((listing, ["IMG_0066.CR2"]), (listing, ["../IMG_0065.CR2"]),
                            (listing, ["IMG_0065.CR2", "IMG_0065.CR2"]),
                            (listing + "::/DCIM/101EOS5D/IMG_0065.CR2\n", ["IMG_0065.CR2"])):
            with self.subTest(text=text, names=names), self.assertRaises(ValueError):
                discover_cr2_paths(text, names)

    def test_completion_requires_the_current_command_ticket(self):
        state = {"flow": {"completed": 4, "completed_ticket": 12}}
        self.assertTrue(request_finished(state, 4, 12))
        self.assertFalse(request_finished(state, 4, 13))
        self.assertFalse(request_finished(state, 7, 12))
        self.assertFalse(request_finished({}, 4, 12))

    def test_oracle_preserves_phase_at_both_borders_and_clamps_outer_margin(self):
        import numpy as np
        from scripts.test_native_capture_sequence import coordinates
        first, second = coordinates(np, 12, 3, True, True)
        self.assertEqual(first.tolist(), [6, 5, 4, 3, 4, 5, 6, 7, 6, 5, 4, 3])
        self.assertEqual(second.tolist(), [8, 7, 6, 5, 4, 5, 6, 7, 8, 7, 6, 5])
        first, second = coordinates(np, 8, 2, False, True)
        self.assertEqual(first.tolist(), [0, 1, 2, 3, 2, 1, 0, 1])
        self.assertEqual(second.tolist(), [0, 1, 2, 3, 4, 3, 2, 1])


if __name__ == "__main__":
    unittest.main()
