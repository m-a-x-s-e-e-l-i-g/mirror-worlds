"""Verify the research JPEG encoder with sanitizers and independent LibRaw decoding.

Requires host Python numpy/rawpy and Linux gcc. Does not exercise a native module
backend or establish camera support. Optional --qemu-run checks captured QEMU data.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.linux_runtime import LinuxRuntime


def dng(jpeg, width, height):
    """Minimal CFA DNG envelope for an independently decoded lossless stream."""
    model = b"Mirror Worlds QEMU 70D\0"
    tags = {
        256: (4, 1, struct.pack("<I", width)), 257: (4, 1, struct.pack("<I", height)),
        258: (3, 1, struct.pack("<H", 14)), 259: (3, 1, struct.pack("<H", 7)),
        262: (3, 1, struct.pack("<H", 32803)), 273: (4, 1, b"xxxx"),
        277: (3, 1, struct.pack("<H", 1)), 278: (4, 1, struct.pack("<I", height)),
        279: (4, 1, struct.pack("<I", len(jpeg))), 284: (3, 1, struct.pack("<H", 1)),
        33421: (3, 2, struct.pack("<HH", 2, 2)), 33422: (1, 4, b"\0\1\1\2"),
        50706: (1, 4, b"\1\4\0\0"), 50707: (1, 4, b"\1\1\0\0"),
        50708: (2, len(model), model), 50710: (1, 3, b"\0\1\2"),
        50711: (3, 1, struct.pack("<H", 1)), 50717: (4, 1, struct.pack("<I", 16383)),
        50721: (10, 9, b"".join(struct.pack("<ii", v, 10000) for v in
                               (10000, 0, 0, 0, 10000, 0, 0, 0, 10000))),
        50728: (5, 3, struct.pack("<IIIIII", 1, 1, 1, 1, 1, 1)),
        50778: (3, 1, struct.pack("<H", 21)),
    }
    tail = bytearray()
    entries = []
    start = 8 + 2 + len(tags) * 12 + 4
    for tag, (kind, count, data) in sorted(tags.items()):
        if len(data) > 4:
            value = struct.pack("<I", start + len(tail))
            tail += data
            if len(tail) % 2:
                tail += b"\0"
        else:
            value = data.ljust(4, b"\0")
        entries.append(struct.pack("<HHI", tag, kind, count) + value)
    strip = start + len(tail)
    entries = [e[:8] + struct.pack("<I", strip) if struct.unpack_from("<H", e)[0] == 273 else e
               for e in entries]
    return (b"II*\0" + struct.pack("<I", 8) + struct.pack("<H", len(tags)) +
            b"".join(entries) + b"\0" * 4 + tail + jpeg)


def decode(jpeg, image, width, height, rawpy):
    image.write_bytes(dng(jpeg, width, height))
    with rawpy.imread(str(image)) as raw:
        return raw.raw_image.copy()


def qemu_pixels(run, out, np, rawpy):
    stream = (run / "jp57-output.ljpeg").read_bytes()
    source = np.fromfile(run / "jp57-input.u16", dtype="<u2").reshape(3708, 5568)
    decoded = decode(stream, out / "qemu-output.dng", 5568, 3708, rawpy)
    assert np.array_equal(decoded, source), "QEMU lossless stream differs from its input"
    # QEMU's generator exposes only bits 16..19, so its noise repeats modulo 2^20.
    period = np.empty(1 << 20, dtype=np.uint16)
    seed = 0x12345678 & ((1 << 20) - 1)
    for i in range(len(period)):
        seed = (seed * 1103515245 + 12345) & ((1 << 20) - 1)
        period[i] = 2048 + ((seed >> 16) & 15) - 8
    x = np.arange(2784, dtype=np.uint32)
    layout_path = run / "jp57-layout.json"
    layout = json.loads(layout_path.read_text()) if layout_path.exists() else {"input_order": "legacy-interleaved"}
    order = layout["input_order"]
    assert order in ("legacy-interleaved", "dma-slices"), "Unknown captured encoder input order"
    if order == "dma-slices":
        planes = source.reshape(2, 3708, 2784)
    for y in range(3708):
        base = (y + 10) * 5648 + 72
        left = planes[0, y] if order == "dma-slices" else source[y, 0::2]
        right = planes[1, y] if order == "dma-slices" else source[y, 1::2]
        assert np.array_equal(left, period[(base + x) & ((1 << 20) - 1)])
        assert np.array_equal(right, period[(base + x + 2784) & ((1 << 20) - 1)])
    return {"kind": "generated-qemu-frame", "pixels_checked": int(source.size),
            "decoded_equals_input": True, "input_equals_independent_sensor_roi": True,
            "stream_sha256": hashlib.sha256(stream).hexdigest(),
            "source_sha256": hashlib.sha256((run / "jp57-input.u16").read_bytes()).hexdigest(),
            "encoder_input_order": order,
            "native_mirror_verified": False, "completed_canon_cr2_verified": False}


def main():
    import numpy as np
    import rawpy
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=("wsl", "docker"), default="wsl")
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--qemu-run", type=Path)
    args = parser.parse_args()
    runtime = LinuxRuntime(ROOT, args.runtime, distro=args.distro)
    output = ROOT / "build/tests/qemu-lossless14"
    output.mkdir(parents=True, exist_ok=True)
    encoder = "targets/70D.112/qemu/lossless14.c"
    flags = ("-std=c99", "-Wall", "-Wextra", "-Werror", "-Wno-misleading-indentation",
             "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-no-pie", "-g", "-O1")
    for name, source in (("encode", "tests/qemu_lossless14_driver.c"),
                         ("bounds", "tests/qemu_lossless14_bounds.c")):
        runtime.run("gcc", *flags, encoder, source, "-o", "build/tests/qemu-lossless14/" + name)
    runtime.run("build/tests/qemu-lossless14/bounds")
    cases = {
        "edges": np.tile(np.array([[0, 16383, 0, 16383], [16383, 0, 16383, 0]], dtype="<u2"), (32, 16)),
        "flat": np.full((32, 64), 2048, dtype="<u2"),
        "ramp": (np.arange(64 * 40, dtype=np.uint16).reshape(40, 64) * 7 % 16384).astype("<u2"),
        "random": np.random.default_rng(70).integers(0, 16384, (64, 128), dtype=np.uint16),
        "sensor": (2048 + ((np.arange(5568 * 3708, dtype=np.uint32) * 1664525 + 1013904223) >> 26))
                  .astype("<u2").reshape(3708, 5568),
    }
    results = []
    for name, pixels in cases.items():
        height, width = pixels.shape
        (output / (name + ".u16")).write_bytes(pixels.tobytes())
        base = "build/tests/qemu-lossless14/" + name
        runtime.run("build/tests/qemu-lossless14/encode", base + ".u16", base + ".ljpeg", str(width), str(height))
        stream = (output / (name + ".ljpeg")).read_bytes()
        decoded = decode(stream, output / (name + ".dng"), width, height, rawpy)
        assert np.array_equal(decoded, pixels), name + ": decoder pixels differ"
        results.append({"name": name, "width": width, "height": height,
                        "pixels_equal": True, "sanitizers": True, "encoded_bytes": len(stream)})
    if args.qemu_run:
        run = args.qemu_run.resolve()
        if not run.is_relative_to(ROOT):
            parser.error("QEMU run must stay within the workspace")
        results.append(qemu_pixels(run, output, np, rawpy))
    report = {"kind": "research-lossless-codec-tests", "runtime": args.runtime,
              "decoder": "LibRaw", "rawpy_version": rawpy.__version__,
              "encoder_sha256": hashlib.sha256((ROOT / encoder).read_bytes()).hexdigest(),
              "bounds_passed": True, "cases": results,
              "module_native_capture_verified": False, "hardware_test": False}
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
