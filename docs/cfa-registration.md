# RAW color-plane registration investigation

## Dev14: preserve exact samples with pixel-centered axes

The owner supplied a dev13 `IMG_9988.CR2` and a close-up showing smoother noise above a fold. Its SHA256 is `e63d340f0ac6857c4f0afc318d60b7c649bddd655cacf0cb2de1a334e7776405`. The card module matches dev13. Direct RAW analysis confirms 6,025,656 top samples and 6,025,656 bottom samples exactly equal the previous kernel's two-neighbor averages. A same-CFA-phase horizontal second-difference measurement gives mirrored/source fine-noise standard-deviation ratios of 0.71710 and 0.71713. The average is reducing noise and fine detail; matching an averaging oracle was insufficient as an image-quality requirement. The local receipt is `.cache/photo-feedback/IMG_9988/averaging-evidence.json`. The private photo is not packaged.

Dev14 replaces averaging with an exact geometric reflection about an integer sensor coordinate. With a border ending just before coordinate `p`, a low edge uses axis `p-1` and maps a destination `x` to `2*(p-1)-x`. A high edge starting at `p` uses axis `p` and maps `x` to `2*p-x`. The same formula applies to rows. The axis moves half a pixel from the old between-sample fold. Every color plane shares that axis, and source parity equals destination parity because `2*axis` is even. This permits original 14-bit samples to be copied unchanged, with no interpolation, clipping, phase-grid extension or old 2x2-cell permutation. The axis sample is a fixed point. All other source samples lie in the untouched center, so vertical folds can copy packed rows directly. Horizontal folds retain the private decoded-row workspace.

The new reference in `tests/registered_raw.c` compares every packed byte against a full out-of-place sample permutation, including random noise, alternating detail, independent color planes, affine ramps, padding and boundary pixels. The new requirement fails against archived dev13 at the first small random-image case. `build/registered-raw/dev14-exact-fold/results.json` records zero mismatches across 3,432 cases on host sanitizers and both ARM CPU models, with 740,608 exact affine samples each. `build/cfa-registration/dev14-pixel-axis/results.json` separately records zero registration/transport errors across all 44 layouts and all 108,416 active samples, including boundaries, on each platform. The historical whole-cell kernel still fails the earlier registration criterion. The full-size capture suite checks the new permutation and the existing cancellation/shutter boundaries.

The preview's integer display fold is retained; the half-sensor-pixel change in RAW fold position is intentional. A new physical-camera capture is still needed to verify demosaiced appearance and saving/review time. A previously averaged photo cannot regain its lost original detail from this module. The earlier interpolation investigation below is retained as history, not as the current pixel policy.

## Earlier interpolation investigation

[EOS M issue #2](https://github.com/m-a-x-s-e-e-l-i-g/mirror-worlds/issues/2) reports a repeating pixel/color pattern and imperfect all-corners symmetry in 0.2.0. Its [JPEG sample](https://i.ibb.co/NnyN974G/sample.jpg) was inspected in the browser. The original CR2 and exact capture/conversion settings are not available in the issue. The cause of that camera report remains unconfirmed.

An independent synthetic test now identifies a related defect in the released and current RAW kernels: preserving each sample's Bayer phase by reversing complete 2×2 cells does not preserve the spatial registration between color planes. The existing transport/pixel oracles specify the cell permutation correctly but do not test that optical requirement.

For example, reversing four two-pixel cells gives source coordinates `6,7,4,5,2,3,0,1`; an ordinary pixel reflection gives `7,6,5,4,3,2,1,0`. The first permutation retains CFA parity but displaces alternating samples by minus/plus one pixel relative to the reflected scene. A spatial ramp therefore creates a two-pixel-period error even though packed values and color parity are intact.

## Controlled reproduction

`tests/cfa_registration.c` constructs a packed Canon14 image whose four CFA planes sample the same affine spatial ramp with fixed per-plane offsets. It runs the actual in-place RAW kernel and independently checks:

- Bit-by-bit packed decoding against the kernel's mapped source coordinates.
- Unchanged data outside the active rectangle.
- The physically reflected ramp value at each destination's original CFA plane.
- A same-CFA-plane interpolation reference using samples from the original packed input. Exact affine checks exclude outer source boundaries, where an extension policy is needed.

The release source is extracted only after verifying the immutable 0.2.0 ZIP and every source-member hash. Current source is copied into a separate diagnostic snapshot. The test does not modify either module binary or release artifact.

```sh
python scripts/analyze_cfa_registration.py --arm --expect-registered
```

Without `--registered`, this command deliberately selects the retained whole-cell kernel and exits unsuccessfully after preserving its evidence. Without `--expect-registered` it produces diagnostic data without claiming that registration passes. The dev7 production edge path uses the registered primitive; test it with the explicit command under Corrective work below. Each run uses a new directory under `build/cfa-registration/`.

The frozen result is `build/cfa-registration/released-and-dev6/results.json`. Both verified 0.2.0 source and dev6 source give the same result under host ASan/UBSan and on the emulator's `arm946-eos` and `arm946-eos5` CPU models:

| Metric per source/platform | Result |
|---|---|
| Mirror layouts checked | 44 |
| Packing/cell-transport mismatches | 0 |
| Affine-ramp registration mismatches | 49,264 |
| Interpolation-reference mismatches in tested interior samples | 0 |

For the diagnostic ramp's slopes of 4 units horizontally and 12 vertically, a horizontal reflection introduces per-phase errors of ±4; a vertical reflection introduces ±12. A doubly reflected corner combines them into phase-dependent errors up to ±16. This provides a deterministic mechanism for an alternating color/detail pattern. It does not establish that this is the only cause of the supplied JPEG's appearance or that its all-corners complaint has been reproduced from a camera CR2.

## Corrective work

The dev7 implementation in `modules/fx_common/fx_mirror_registered.c` samples the desired reflected position on each destination CFA plane. It applies vertical then horizontal half-up averages; the outer active rectangle uses constant extension independently for each CFA phase. Interpolation changes sharp detail, so exact linear registration does not imply lossless reflection of arbitrary high-frequency detail.

The primitive retains both original fold-seam rows in a two-packed-row workspace, then keeps the two original seam samples while processing each horizontal row. No full-frame copy or allocation occurs inside the transform. It validates before writing and checks cancellation before mutation; after the first write it completes the frame. Unlike whole-cell reversal, applying this interpolation twice can change seam samples, so the capture gate applies it once per accepted shutter latch.

`tests/registered_raw.c` compares the actual in-place output with a separate out-of-place separable reference using independent bit-by-bit packing. Across 3,432 cases it checks all 44 legal layouts, six input patterns, tiny and offset regions, exact thirds and remainder seams, pitch padding, clipping endpoints, guards, malformed maps, overlaps and cancellation. The frozen `build/registered-raw/reference-v3/results.json` records identical results under host ASan/UBSan and both ARM CPU models: zero mismatches and 708,776 exact interior affine samples per platform. That snapshot predates capture integration.

```sh
python scripts/test_registered_raw.py --arm
python scripts/analyze_cfa_registration.py --arm --registered --expect-registered
```

The second command runs the immutable release, the old working cell kernel, and the new primitive separately. In `build/cfa-registration/registered-v1/results.json`, each platform records 48,168 **interior** registration errors for the old kernel and zero for the registered primitive across the same 104,464 interior samples. All three kernels' packing/reference checks pass. At the boundary, the new primitive has 200 deviations from extrapolating the ramp beyond the available same-phase samples; all match the explicitly tested constant-extension reference. The total 49,264 old errors above remains the original metric, including boundaries. The stricter interior metric separates registration from boundary policy rather than hiding that difference.

Dev7 connects the primitive to the existing native capture gate for rectangular edge controls. The first shutter edge borrows the preview-memory lease before Canon exits LiveView; preparation, rendering and teardown cannot reuse its canvas while held. Completion and every pre-write refusal release it. Cancellation/shutdown during a held callback retain the arena until that callback returns; a missed callback releases it when the unchanged five-second latch deadline expires. Fixed historical angular diagnostic controls retain the old kernel. The lease owns only private workspace; existing Canon readout/context/observer checks still govern sensor access, and no new Canon ownership or timing claim follows from it.

The frozen host capture receipt is `build/registered-raw/dev7-capture-integration/results.json`. Its sanitizer run checks all 44 full-size layouts on both EOS M and the isolated 70D backend against the interpolation reference, plus refusal before writes and lease cleanup. The actual loaded dev7 module also passes 88 small RAW cases through ML's cross-module loader in `build/compatibility/dev7-registered-matrix-v1/results.json`. Neither run is a successful camera CR2 capture with the new algorithm.

## Per-shot cancellation follow-up

Dev7 had two cancellation gaps in the capture integration. During a held callback, automatic OFF followed by ON cleared `gate.cancel`, reviving that cancelled shot. The regression in `tests/camera_portability.c` reports scenario 15 completing successfully with `started=1, done=1` against dev7 when it must refuse with `MG_CANCEL`. Separately, the gate prepared its RAW map with `stop=NULL`, so cancellation during the primitive's workspace preflight was not visible to its final pre-write check. The new `tests/capture_delivery.c` assertion also fails when compiled against the frozen dev7 source.

Dev8 preserves cancellation while the callback is held and passes a private per-shot stop flag into RAW preparation. Both cancel and shutdown set that flag. The first-write boundary remains deliberate: cancellation before writes preserves every source byte; cancellation after a write completes the same output as an uninterrupted transform. The fixture attempts preview teardown inside the first-write hook and verifies the lease retains its memory until the callback finishes. Separate runs cover shutdown while armed and during RAW preflight. These are compiled SDK fixtures, not physical-camera concurrency/timing proof.

Run `python scripts/test_capture_cancellation.py` to replay both regressions against the hash-verified dev7 r2 source archive and current built source. The frozen `build/capture-cancellation/dev8-before-after-v1/results.json` records the two specific expected dev7 assertions and all three working-source checks passing. It snapshots the compared source, fixtures, compiled binaries and logs. A compiler error, unrelated crash, or different assertion cannot count as a successful reproduction.

The dev6 candidate and camera-tested 0.2.0 release remain byte unchanged. Dev7 still needs original-versus-effect EOS M CR2 captures, capture settings and converter details before issue #2 can be described as fixed on hardware. In-camera JPG output requested in issue #3 is a separate feature.

Dev9 [reduces RAW instruction cost](raw-processing-cost.md) by processing full packed groups and reusing the same workspace as a decoded horizontal source row. Its output matches the dev8 interpolation policy; it does not change rounding, boundaries, the cancellation contract or the camera-validation requirement.
