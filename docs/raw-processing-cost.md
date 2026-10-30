# RAW processing instruction cost

## Dev14 exact-sample fold

The owner's dev13 CR2 confirms visible smoothing by the interpolation kernel. Dev14 replaces it with exact-sample reflection about pixel-centered axes, as described in [the quality investigation](cfa-registration.md#dev14-preserve-exact-samples-with-pixel-centered-axes). It retains grouped Canon14 access and partial source-band decoding. Vertical folds now copy packed row intervals directly; horizontal folds copy decoded samples without calculating averages.

`build/registered-cost/dev14-vs-dev13/results.json` compares the hash-verified dev13 candidate with dev14 on the same synthetic EOS M-sized frame and default-crop rectangle. Both CPU models agree:

| Layout | Dev13 counter ticks | Dev14 counter ticks | Reduction |
|---|---:|---:|---:|
| Right / Half | 240,456 | 179,222 | 25.5% |
| Top / Half | 118,753 | 2,964 | 97.5% |
| All edges / Third | 427,718 | 188,697 | 55.9% |

The output checksums deliberately differ because interpolation has been removed and axes move half a pixel. `--allow-output-change` is restricted to the dev13 baseline and records this difference; it does not attest correctness. The separate exact-sample and registration oracles validate the new output. These are instruction-cost measurements, with no modeled sensor-bus/cache latency or Canon saving time. In particular, the large packed-row-copy reduction is not a prediction of camera speedup. Capture-gate checks and deadlines remain unchanged.

```sh
python scripts/measure_registered_cost.py --baseline-version dev13 --allow-output-change --output build/registered-cost/dev14-vs-dev13
```

## Earlier dev12 averaging optimization

Dev12 responds to the EOS M owner's report that dev11 captures successfully but takes more than three seconds to show the photo. It keeps dev11's working half-shutter latch and its separate 18,480-byte private RAW workspace. The capture gate, its 100 ms scheduling probe, observer checks and deadlines are unchanged. The optimization is confined to the registered RAW kernel:

- Horizontal processing decodes only the source bands needed by the selected folds, including interpolation neighbors. Both bands are cached before either destination is written, and overlapping bands are decoded once.
- Vertical processing averages two packed 14-bit samples at once with independent lane rounding, avoiding per-sample temporary arrays in the aligned ARM path.
- Complete Canon14 groups use three aligned 32-bit accesses plus one 16-bit access instead of seven 16-bit accesses where applicable. Odd-address buffers retain the byte-safe fallback.

`build/registered-cost/dev12-final-vs-dev11/results.json` compares the hash-verified dev11 candidate source with dev12 using the same procedure below. Both CPU models produce the same results and full-buffer checksums:

| Layout | Dev11 counter ticks | Dev12 counter ticks | Reduction |
|---|---:|---:|---:|
| Right / Half | 292,334 | 240,456 | 17.7% |
| Top / Half | 245,053 | 118,753 | 51.5% |
| All edges / Third | 671,888 | 427,718 | 36.3% |

These reductions concern synthetic guest instructions, not wall-clock camera saving/review time. The owner has confirmed dev11 capture, but has not yet measured dev12. Compare both versions with the same scene, exposure, card, file format and effect settings. The independent 3,432-case reference runs on the host with sanitizers and both ARM CPU models; actual gate integration separately checks full-size RAW layouts and cancellation.

```sh
python scripts/measure_registered_cost.py --baseline-version dev11 --output build/registered-cost/dev12-final-vs-dev11
```

## Earlier dev9 comparison

Dev9 reduces the shared registered RAW kernel's instruction cost without changing its output or increasing its workspace. Vertical processing reads and writes complete eight-sample Canon14 groups. After the vertical pass, the same two-row workspace holds one decoded row, so horizontal processing reads original samples from private memory and packs complete output groups. Odd-address workspace retains the scalar fallback.

The immutable dev8 source is extracted from its hash-verified candidate archive. Both versions are compiled with the same ARMv5TE / `-O2` flags and executed on QEMU's `arm946-eos` and `arm946-eos5` CPU models. Each case uses a synthetic 5280×3528 packed frame and the EOS M active rectangle. A VersatilePB SP804 timer brackets the kernel only; input initialization, checksumming and output are excluded.

QEMU runs with `-icount shift=0,align=off,sleep=off`: one guest instruction advances its virtual clock by one nanosecond. The timer defaults to 1 MHz in the pinned emulator source. Its counter therefore provides a scaled instruction-cost comparison. These are **not camera microseconds**, and neither CPU caches nor sensor-bus latency is modeled. The executable is a source-kernel fixture, separate from the loaded-module checks.

The final receipt is `build/registered-cost/dev9-grouped-v2/results.json`. Both CPU models give identical measurements:

| Layout | Dev8 counter ticks | Dev9 counter ticks | Old/new cost |
|---|---:|---:|---:|
| Right / Half | 1,128,817 | 292,334 | 3.86× |
| Top / Half | 770,477 | 245,053 | 3.14× |
| All edges / Third | 2,556,127 | 671,888 | 3.80× |

All three full-buffer output checksums match between versions. Correctness is also checked independently of checksums: `tests/registered_raw.c` compares every byte with an out-of-place interpolation reference across 3,432 cases under host ASan/UBSan and on both ARM CPU models. It covers unaligned pitches, odd-address workspace, group-prefix/tail packing, margins, guards, and pre/post-write cancellation. The actual capture-gate suite separately checks all 44 full-size EOS M layouts and all 44 research-only 70D layouts.

```sh
python scripts/measure_registered_cost.py
python scripts/test_registered_raw.py --arm
python scripts/test_portability.py --runtime wsl --sanitize
```

The comparison command needs the retained dev8 candidate at `build/candidates/MIRROR-0.3.0-dev8-OFFICIAL-LV-CANDIDATE.zip`; it does not fetch a replacement or overwrite old evidence. Fresh results live under `build/registered-cost/`.

Dev9 leaves the capture gate's five-second shutter-latch deadline and two-second post-hoc full-frame hold limit unchanged. Real EOS M capture timing and CR2 output still need owner validation. Lower emulated instruction cost does not establish that a particular camera meets that limit.
