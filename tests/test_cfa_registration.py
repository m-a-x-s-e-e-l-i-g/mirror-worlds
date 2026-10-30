import json
import unittest
from scripts.analyze_cfa_registration import diagnostic


class CfaRegistrationDiagnosticTest(unittest.TestCase):
    def evidence(self):
        cases=[{"mask":2,"dx":i,"dy":2,"transport_mismatches":0,"registration_mismatches":10,"reference_mismatches":0,"reference_samples":20,"interior_registration_mismatches":8,"boundary_extension_samples":2} for i in range(44)]
        total={"cases":44,"transport_mismatches":0,"registration_mismatches":440,"reference_mismatches":0,"reference_samples":880,"interior_registration_mismatches":352,"boundary_extension_samples":88}
        return cases,total

    def text(self,cases,total):
        return "\n".join("CFA_CASE="+json.dumps(c) for c in cases)+"\nCFA_TOTAL="+json.dumps(total)

    def test_valid_transport_does_not_hide_optical_registration_errors(self):
        cases,total=self.evidence();r=diagnostic(self.text(cases,total))
        self.assertEqual(r["totals"]["registration_mismatches"],440)

    def test_missing_duplicate_and_inconsistent_evidence_is_rejected(self):
        cases,total=self.evidence()
        with self.assertRaisesRegex(ValueError,"Incomplete"):diagnostic(self.text(cases[:-1],total))
        cases[-1]=cases[0]
        with self.assertRaisesRegex(ValueError,"Duplicate"):diagnostic(self.text(cases,total))
        cases,total=self.evidence();total["registration_mismatches"]=0
        with self.assertRaisesRegex(ValueError,"totals"):diagnostic(self.text(cases,total))


if __name__=="__main__":unittest.main()
