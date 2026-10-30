import copy
import unittest
from scripts.test_main_registered_capture import check_completed_gate


class RegisteredMainCaptureTest(unittest.TestCase):
    def evidence(self):
        return {"gate": {"phase": 4, "error": 0, "installed": 1, "latched": 1, "sample_mode": 3,
            "params": [180, 2, 2, 2], "patch_started": 1, "patch_done": 1, "patch_verified": 896,
            "patch_mismatches": 0, "overlaps": 0, "changed": 0, "before_count": 896, "after_count": 896,
            "patch_changed": 434, "enter_us": 56556288, "full_ms": 56312, "release_us": 56888320,
            "held_us": 332032, "patch_us": 220672, "source": 0x41000000, "dma_address": 0x1000000 + 9884,
            "dma_pointer": 0x1000000 + 9884 + 36768480, "dma_before": 0, "dma_after": 0,
            "context": 0x7c15c, "lr": 0xff15c4d0, "cpsr": 0x60000013},
            "workspace": {"held": 0, "gate_data": 0},
            "raw_map": {"frame": {"format": 1, "height": 3720, "pitch": 9884, "size": 36768480, "width": 5648},
                        "region": [60, 156, 3708, 5628]}}

    def test_only_this_completed_capture_is_accepted(self):
        self.assertAlmostEqual(check_completed_gate(self.evidence()), 244.288)
        for key, value in (("error", 7), ("patch_done", 0), ("patch_verified", 895), ("patch_mismatches", 1),
                           ("overlaps", 1), ("changed", 1), ("phase", 5), ("params", [180, 15, 3, 3]),
                           ("dma_pointer", 0), ("dma_after", 1), ("context", 0), ("cpsr", 0x93)):
            evidence = self.evidence()
            evidence["gate"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_completed_gate(evidence)

    def test_timing_workspace_and_geometry_cannot_be_ignored(self):
        for path, value in ((["gate", "full_ms"], 46000), (["gate", "held_us"], 1),
                            (["gate", "patch_us"], 0), (["workspace", "held"], 1),
                            (["workspace", "gate_data"], 0x1234), (["raw_map", "region"], [0, 0, 2, 2])):
            evidence = copy.deepcopy(self.evidence())
            evidence[path[0]][path[1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                check_completed_gate(evidence)
