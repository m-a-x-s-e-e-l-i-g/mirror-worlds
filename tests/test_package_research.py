import json
from pathlib import Path
import tempfile
import unittest

from tools.package_module import package_module


class ResearchPackageTest(unittest.TestCase):
    def test_research_module_refused_before_artifact_audit_or_publication(self):
        for marker in ({"research_70d": True}, {"kind": "emulator-only-70d-module"}):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                build = root / "build/modules/mirror"
                build.mkdir(parents=True)
                (build / "build.json").write_text(json.dumps(marker))
                with self.assertRaisesRegex(RuntimeError, "unshipped 70D research module"):
                    package_module("mirror", root=root, candidate=True)
                self.assertFalse((root / "releases").exists())
                self.assertFalse((root / "build/candidates").exists())


if __name__ == "__main__":
    unittest.main()
