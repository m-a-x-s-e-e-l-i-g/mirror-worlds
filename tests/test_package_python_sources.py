from pathlib import Path
import tempfile
import unittest
from tools.package_module import complete_python_sources


class CandidatePythonSourcesTest(unittest.TestCase):
    def write(self, root, name, text):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_transitive_absolute_relative_and_script_imports_are_included(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            test = self.write(root, "tests/test_demo.py", "from scripts.driver import run\n")
            self.write(root, "scripts/driver.py", "from tools.worker import run\nfrom local_helper import value\n")
            self.write(root, "scripts/local_helper.py", "import json\nvalue=1\n")
            self.write(root, "tools/worker.py", "from .shared import run\n")
            self.write(root, "tools/shared.py", "from tools.worker import run\nimport pathlib\n")
            self.write(root, "tools/unrelated.py", "raise Exception('must not be read or executed')\n")
            files = {"source/tests/test_demo.py": test}
            complete_python_sources(files, root)
            self.assertEqual(set(files), {"source/" + name for name in (
                "tests/test_demo.py", "scripts/driver.py", "scripts/local_helper.py", "tools/worker.py", "tools/shared.py")})

    def test_missing_local_dependency_is_rejected_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.write(root, "tests/test_demo.py", "raise Exception('not executed')\nfrom tools.missing import value\n")
            with self.assertRaisesRegex(ValueError, "Missing local Python"):
                complete_python_sources({"source/tests/test_demo.py": path}, root)

    def test_parent_import_cannot_escape_the_package_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.write(root, "tools/driver.py", "from ...outside import secret\n")
            with self.assertRaisesRegex(ValueError, "escapes workspace"):
                complete_python_sources({"source/tools/driver.py": path}, root)


if __name__ == "__main__":
    unittest.main()
