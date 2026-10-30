# Mirror Worlds upstream review bundle

This bundle adds a self-contained `modules/mirror/` subtree to Magic Lantern. Its `shared/` renderer and `engine/` helpers live inside that subtree. Copying it into upstream requires no files from this repository's sibling module folders and no core/platform changes. The normal build produces an API-8 ARMv5TE module with runtime camera/firmware selection.

Native mirrored Canon CR2 capture remains implemented for the original EOS M / Canon 2.0.2. Other eligible profiles provide LiveView preview; saved photos remain original. Unknown model/firmware combinations refuse initialization. Additional cameras still require owner validation. The historical API-7 experiment is a separate build and is not the default module in this proposal.

## Apply and build

Use a clean checkout of [Magic Lantern at 142472e95054d73640f50789ac0fd66325499d82](https://github.com/reticulatedpines/magiclantern_simplified/tree/142472e95054d73640f50789ac0fd66325499d82). With the GNU ARM toolchain and upstream build dependencies installed:

```sh
git apply --check /path/to/mirror-upstream.patch
git apply /path/to/mirror-upstream.patch
make -C modules/mirror
```

Alternatively, copy the bundle's `source/modules/mirror/` into that checkout. The patch adds only this module subtree. It does not enable the module in default camera builds.

The export verifier applies this patch to a newly extracted pinned upstream tree, builds with warnings treated as errors, and checks the compiler's actual dependency files for platform-header leakage. After fixing generated build date/user metadata through the project's reproducible build recipe, the clean build must reproduce the dev9 candidate SHA-256:

```text
fb09df85a94ffe274a0f70d2415193a9971ec08b4efaeb4174d2950c5830c449
```

Ordinary upstream builds embed their current build date/user. Byte comparisons require the same normalized metadata. `plan.json` records the source epoch; `results.json` records export hashes, compiler identity, patch/build checks and the resulting module hash.

## Review points

- `mirror_camera.c` selects exact model/firmware profiles before initialization. Its EOS M firmware addresses are private backend data; native requests and DMA reads require that selected backend. The optional 70D research flag is off in the default build.
- Core interactions use scalar APIs and runtime dimensions. The normal build's imports and 23 used shared fields match 14 source-built firmware cores. The pinned 7D core still has an upstream build blocker; the cached older 7D distribution also uses API 7.
- `mirror.c` registers the normal display/key/property hooks and a worker. It preserves Canon's shutter, review and playback controls. Dev6 seeds the initial Canon GUI state and waits for a fresh frame after each ON before reporting preview delivery.
- The module owns its preview allocations and keeps a DMA reserve plus a contiguous-block preflight. It does not retain a photo/SRM fallback pool for preview.
- Dev7 interpolates reflected RAW positions within each destination CFA plane. Two packed rows borrowed from the private preview canvas retain original seam neighbors. The shutter latch acquires that lease before LV exit; completion, refusal, cancellation and timeout release it. This changes sharp RAW detail and requires new EOS M CR2/timing validation.
- Dev8 keeps the current shot cancelled even if the effect is re-enabled during its held callback. Its stop flag reaches the RAW primitive's last pre-write check; cancellation after writes begin still completes the frame before releasing workspace.
- Dev9 processes complete Canon14 groups and reuses that same workspace for horizontal source samples. Its measured instruction-cost reduction is from a separate source-kernel fixture, not a physical-camera timing claim; independent pixel and cancellation oracles remain required.
- Shared code stays privately namespaced in this first contribution. Kaleido is absent from this repository, and older EOS M loaders lack automatic dependency loading; a hidden shared library is a separate integration decision.

The host suite checks selection, startup/review transitions, preferences, memory cleanup and independent preview/RAW pixel oracles. The available 70D firmware emulator loads the normal module, exercises its real menu, renders owned synthetic buffers through the loaded binary and completes OFF cleanup. Canon's real LiveView frame stream is still unavailable in that run. These results do not establish additional hardware compatibility or native capture outside EOS M.

Regenerate the bundle from the development repository after building the normal upstream module:

```sh
python -m tools.export_upstream_module
```

Outputs use a fresh directory under `build/upstream-export/`. Existing candidates and the released 0.2.0 artifacts are preserved. This is a local review artifact; it does not create or publish a pull request.
