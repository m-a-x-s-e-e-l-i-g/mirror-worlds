"""Source in GDB, then run mirror70d-observe before a virtual 70D release.

Sets debugger breakpoints; does not queue a photo, write pixels or change CPU
registers. Stops at the lossless descriptor. Emulator state is not a buffer lease.
"""
import json
import struct
import gdb


def _words(address, count):
    data = bytes(gdb.selected_inferior().read_memory(address, count * 4))
    return list(struct.unpack("<%dI" % count, data))


def _register(name):
    return int(gdb.parse_and_eval("$" + name)) & 0xffffffff


class _NativeProbe(gdb.Breakpoint):
    def __init__(self, address, label, records):
        super().__init__("*" + hex(address), internal=True)
        self.label = label
        self.records = records

    def stop(self):
        record = {"kind": "emulator-native-binding-observation", "model": "70D",
                  "firmware": "1.1.2", "phase": self.label, "hardware_test": False,
                  "sensor_ownership_verified": False, "observer_writes_pixels": False,
                  "registers": {name: hex(_register(name)) for name in
                                ("r0", "r4", "r10", "lr", "pc", "cpsr")}}
        if self.label == "stage":
            if _register("r10") != 0x7c15c or _register("lr") != 0xff15c4d0:
                raise gdb.GdbError("Unexpected 70D stage caller/context; observation stopped")
            record["job"] = hex(_words(0x7c208, 1)[0])
            record["edmac0_words"] = [hex(x) for x in _words(0xc0f04000, 12)]
        else:
            if _register("r4") != 0xc1770:
                raise gdb.GdbError("Unexpected 70D lossless descriptor; observation stopped")
            descriptor = _words(0xc1770, 48)
            record["descriptor"] = "0xc1770"
            record["width"] = descriptor[0x38 // 4] >> 16
            record["height"] = descriptor[0x3c // 4] & 65535
            record["precision"] = descriptor[0x40 // 4]
            for name, offset in (("source1", 0x58), ("offset1", 0x5c),
                                 ("source2", 0x70), ("offset2", 0x74)):
                record[name] = hex(descriptor[offset // 4])
        self.records.append(record)
        self.enabled = False
        gdb.write("MIRROR_QEMU_NATIVE=" + json.dumps(record, sort_keys=True) + "\n")
        return self.label == "lossless_descriptor"


class _Observe70D(gdb.Command):
    def __init__(self):
        super().__init__("mirror70d-observe", gdb.COMMAND_USER)
        self.probes = []
        self.records = []

    def invoke(self, argument, from_tty):
        if argument.strip():
            raise gdb.GdbError("Usage: mirror70d-observe")
        if any(probe.is_valid() and probe.enabled for probe in self.probes):
            raise gdb.GdbError("A 70D observation is already armed")
        reply = gdb.execute("maintenance packet qqemu.sstepbits", to_string=True)
        if "ENABLE=" not in reply or "NOIRQ=" not in reply or "NOTIMER=" not in reply:
            raise gdb.GdbError("QEMU remote extension not found; no breakpoints installed")
        guards = {
            0xff361910: [0xe12fff1e, 0xe3a00000, 0xe12fff1e, 0xe12fff1e],
            0xff15c4cc: [0xeb08150f, 0xe59a402c, 0xe2840d0d, 0xe58d0198],
            0xff437d58: [0xe5940058, 0xe3500000, 0x0a00000d, 0xe5940048],
        }
        for address, expected in guards.items():
            if _words(address, 4) != expected:
                raise gdb.GdbError("70D instruction guard failed at " + hex(address))
        self.records = []
        self.probes = [_NativeProbe(0xff361910, "stage", self.records),
                       _NativeProbe(0xff437d58, "lossless_descriptor", self.records)]
        gdb.write("70D observer armed; trigger the virtual release, then continue.\n")


mirror70d_observer = _Observe70D()
