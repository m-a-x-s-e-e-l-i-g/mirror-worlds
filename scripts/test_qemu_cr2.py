"""Check the research Eeko adapter and optionally an actual Canon-saved virtual CR2.

Host Python requires numpy, rawpy and Pillow; Linux requires gcc. Generated QEMU
sensor data and placeholder previews do not establish native module/hardware support.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.linux_runtime import LinuxRuntime
from test_qemu_lossless import qemu_pixels


def tiff_ifds(data):
    assert data[:4] == b"II*\0" and data[8:12] == b"CR\2\0", "Expected Canon CR2"
    offset = struct.unpack_from("<I", data, 4)[0]
    seen, tables = set(), []
    while offset:
        assert offset not in seen and len(tables) < 8 and offset + 2 <= len(data)
        seen.add(offset)
        count = struct.unpack_from("<H", data, offset)[0]
        assert offset + 2 + count * 12 + 4 <= len(data)
        table = {}
        for i in range(count):
            at = offset + 2 + i * 12
            tag, kind, n, value = struct.unpack_from("<HHII", data, at)
            assert tag not in table
            if kind not in (1, 2, 3, 4, 5, 7, 9, 10):
                continue
            size = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}[kind] * n
            start = at + 8 if size <= 4 else value
            assert start + size <= len(data)
            payload = data[start:start + size]
            table[tag] = (list(struct.unpack("<" + ("H" if kind == 3 else "I") * n, payload))
                          if kind in (3, 4) else payload)
        tables.append(table)
        offset = struct.unpack_from("<I", data, offset + 2 + count * 12)[0]
    return tables


def check_cr2(run, out):
    import numpy as np
    import rawpy
    from PIL import Image
    files = list(run.glob("*.CR2"))
    assert len(files) == 1, "Extract exactly one Canon-saved CR2 from the stopped VM"
    log = (run / "qemu.log").read_text(errors="replace")
    for text in ("CompleteMem1ToJpegCB", "synthetic flat thumbnail 160x120: 260 bytes",
                 "completed pending output pop on channel 22", "Write1Complete(POP)CBR",
                 files[0].name + " write done"):
        assert text in log, "Missing Canon/emulator completion: " + text
    assert "ASSERT :" not in log and "MEMTX invalid" not in log
    layout = json.loads((run / "jp57-layout.json").read_text())
    assert layout == {"input_order": "dma-slices", "slices": 2, "slice_width": 2784, "height": 3708}
    codec = qemu_pixels(run, out, np, rawpy)
    data = files[0].read_bytes()
    tables = tiff_ifds(data)
    assert len(tables) == 4
    raw_ifd = tables[3]
    assert raw_ifd[256] == [5568] and raw_ifd[257] == [3708]
    assert raw_ifd[0xc640] == [1, 2784, 2784], "Unexpected Canon slice mapping"
    start, size = raw_ifd[273][0], raw_ifd[279][0]
    assert data[start:start + size] == (run / "jp57-output.ljpeg").read_bytes()
    planes = np.fromfile(run / "jp57-input.u16", dtype="<u2").reshape(2, 3708, 2784)
    expected = np.concatenate((planes[0], planes[1]), axis=1)
    with rawpy.imread(str(files[0])) as raw:
        decoded = raw.raw_image.copy()
        assert decoded.shape == expected.shape and np.array_equal(decoded, expected), "Canon CR2 pixel/slice mismatch"
        sizes = raw.sizes._asdict()
        pattern = raw.raw_pattern.tolist()
        thumb = raw.extract_thumb()
    previews = []
    for name, jpeg, dimensions in (("preview", thumb.data, (5472, 3648)),
                                  ("thumbnail", data[tables[1][513][0]:tables[1][513][0]+tables[1][514][0]], (160, 120))):
        with Image.open(io.BytesIO(jpeg)) as image:
            image.load()
            assert image.size == dimensions and image.mode == "L" and image.getextrema() == (128, 128)
        (out / (name + ".jpg")).write_bytes(jpeg)
        previews.append({"name": name, "dimensions": dimensions, "synthetic_gray_level": 128})
    return {"kind": "canon-saved-virtual-cr2", "file": files[0].relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "raw_strip_equals_encoder_stream": True, "raw_pixels_checked": int(decoded.size),
            "cr2_pixels_equal_sensor_roi": True, "slices": raw_ifd[0xc640],
            "decoder_sizes": sizes, "decoder_cfa": pattern, "codec": codec, "previews": previews,
            "completed_canon_cr2_verified": True, "native_mirror_verified": False,
            "sensor_ownership_verified": False, "hardware_test": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=("wsl", "docker"), default="wsl")
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--qemu-run", type=Path)
    args = parser.parse_args()
    runtime = LinuxRuntime(ROOT, args.runtime, distro=args.distro)
    out = ROOT / "build/tests/qemu-eeko-lcd"
    out.mkdir(parents=True, exist_ok=True)
    runtime.run("gcc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                "-fno-sanitize-recover=all", "-no-pie", "-g", "-O1", "tests/qemu_eeko_lcd_bounds.c",
                "-o", "build/tests/qemu-eeko-lcd/bounds")
    runtime.run("build/tests/qemu-eeko-lcd/bounds")
    result = {"adapter_sanitizers_and_bounds_passed": True, "hardware_test": False}
    if args.qemu_run:
        run = args.qemu_run.resolve()
        if not run.is_relative_to(ROOT):
            parser.error("QEMU run must stay within the workspace")
        result["cr2"] = check_cr2(run, out)
    (out / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
