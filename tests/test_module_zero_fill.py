from pathlib import Path
import struct
import unittest

from tools.audit_module import inspect_module

ROOT = Path(__file__).resolve().parents[1]


class ModuleZeroFillTest(unittest.TestCase):
    def empty_property_table_in_bss(self):
        fixture = ROOT / "downloads/mirror.mo"
        if not fixture.is_file():
            # A candidate archive keeps its actual ELF beside source/, rather
            # than including a second release binary just for this fixture.
            fixture = ROOT.parent / "ML/MODULES/mirror.mo"
        data = bytearray(fixture.read_bytes())
        header = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
        sections = [struct.unpack_from("<10I", data, header[6] + i * 40) for i in range(header[12])]
        bss = next(i for i, section in enumerate(sections) if section[1] == 8 and section[5] >= 4)
        for table in sections:
            if table[1] != 2:
                continue
            strings = sections[table[6]]
            for offset in range(table[4], table[4] + table[5], 16):
                name, value, size, info, other, section = struct.unpack_from("<IIIBBH", data, offset)
                start = strings[4] + name
                if bytes(data[start:data.find(b"\0", start)]) == b"__module_prophandlers_mirror":
                    struct.pack_into("<IIIBBH", data, offset, name, 0, 4, info, other, bss)
                    # File offset is not storage for NOBITS. Point it at the
                    # nonzero ELF header to catch accidental on-disk reads.
                    struct.pack_into("<I", data, header[6] + bss * 40 + 16, 0)
                    return data, header[6] + bss * 40
        self.fail("Fixture lacks property metadata")

    def test_empty_property_table_uses_loader_zero_initialization(self):
        data, _ = self.empty_property_table_in_bss()
        report = inspect_module(data)
        self.assertEqual(report["property_handlers"], [])
        # Definitions still need registration; zero-fill must not hide them.
        self.assertTrue(report["unregistered_property_handlers"])

    def test_excessive_zero_fill_is_rejected_without_allocating_it(self):
        data, bss_header = self.empty_property_table_in_bss()
        struct.pack_into("<I", data, bss_header + 20, 0xFFFFFFFF)
        with self.assertRaisesRegex(ValueError, "zero-fill section exceeds audit limit"):
            inspect_module(data)

    def test_api7_requires_an_explicit_audit_target(self):
        data, _ = self.empty_property_table_in_bss()
        h = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
        sections = [struct.unpack_from("<10I", data, h[6] + i * 40) for i in range(h[12])]
        found = False
        for table in sections:
            if table[1] != 2:
                continue
            names = sections[table[6]]
            for at in range(table[4], table[4] + table[5], 16):
                name, value, _, _, _, section = struct.unpack_from("<IIIBBH", data, at)
                start = names[4] + name
                if bytes(data[start:data.find(b"\0", start)]) == b"__module_info_mirror":
                    data[sections[section][4] + value + 1] = 7
                    found = True
        self.assertTrue(found)
        with self.assertRaisesRegex(ValueError, "module API"):
            inspect_module(data)
        self.assertEqual(inspect_module(data, api_major=7)["module_api"], [90, 7, 0, 0])
        with self.assertRaisesRegex(ValueError, "module API"):
            inspect_module(data, api_major=9)


if __name__ == "__main__":
    unittest.main()
