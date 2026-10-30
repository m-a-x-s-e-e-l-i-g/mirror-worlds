from pathlib import Path
import tempfile
import unittest

from tools.export_upstream_module import module_inputs, new_file_patch, original_input


class UpstreamExportTest(unittest.TestCase):
    def stage(self, root):
        stage = root / "modules/mirror"
        (stage / "build").mkdir(parents=True)
        (stage / "shared").mkdir()
        for name in ("README.rst", "mirror_native_disabled.c", "mirror.c", "shared/fx_namespace.h"):
            (stage / name).write_text("/* fixture */\n")
        (stage / "Makefile").write_text("MODULE_OBJS = $(BUILD_DIR)/mirror.o\n")
        (stage / "build/mirror.d").write_text("build/mirror.o: mirror.c shared/fx_namespace.h ../../src/module.h build/module_strings.h\nshared/fx_namespace.h:\n")
        return stage

    def test_dependency_closure_ignores_generated_and_stale_build_files(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = self.stage(Path(directory))
            (stage / "build/old.d").write_text("old.o: ../../platform/7D.203/consts.h\n")
            self.assertEqual(module_inputs(stage), ["Makefile", "README.rst", "mirror.c", "mirror_native_disabled.c", "shared/fx_namespace.h"])

    def test_camera_specific_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = self.stage(Path(directory))
            with (stage / "build/mirror.d").open("a") as file:
                file.write("mirror.o: ../../platform/7D.203/consts.h\n")
            with self.assertRaisesRegex(ValueError, "SDK boundary"):
                module_inputs(stage)

    def test_patch_paths_and_input_mapping_preserve_the_module_boundary(self):
        patch = new_file_patch("modules/mirror/shared/a.h", b"first\nsecond\n")
        self.assertIn("+++ b/modules/mirror/shared/a.h\n@@ -0,0 +1,2 @@\n+first\n+second\n", patch)
        with self.assertRaises(ValueError):
            new_file_patch("../outside.h", b"unsafe\n")
        self.assertEqual(original_input("shared/fx_camera.c"), "modules/fx_common/fx_camera.c")
        self.assertEqual(original_input("engine/glitchlock.h"), "core/glitchlock.h")
        self.assertEqual(original_input("engine/gl_format.c"), "modules/glock/gl_format.c")


if __name__ == "__main__":
    unittest.main()
