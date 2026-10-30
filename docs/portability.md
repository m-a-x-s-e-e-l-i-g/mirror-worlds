# Camera portability candidate (0.3.0-dev)

The owner accepted dev14's EOS M capture and image quality for the **0.3.0 release**. The release retains that processing code with a stable version label; subsequent entries below record the development history. EOS M is the only camera-tested native RAW target. Additional-camera preview profiles, API-7 experiments and 70D native research remain experimental. See the [release notes](release-0.3.0.md) and [usage guide](usage.md).

Dev14 replaces RAW averaging after the owner supplied a dev13 CR2 showing blurred grain in mirrored areas. Direct analysis confirms exact two-neighbor averages and about 28% lower fine-noise contrast. The new fold copies original samples around integer sensor axes, moving each fold by half a pixel while keeping all color planes aligned. It retains the full decoder-visible bounds, half-shutter fix, private workspace and cancellation checks. [Exact-sample and registration tests](cfa-registration.md#dev14-preserve-exact-samples-with-pixel-centered-axes) pass on host sanitizers and both ARM CPU models. Dev14 demosaiced appearance and actual camera timing remain unconfirmed.

Dev13 expands only the EOS M RAW output rectangle after the owner's CR2 revealed an unmirrored outer strip. The previous rectangle matched Canon's default JPEG crop; the new rectangle covers LibRaw's full 5208x3476 visible image at (72,52). Optical-black rows/columns remain outside processing. The [RAW bounds investigation](eosm-raw-bounds.md) records an exact 11,923,200-pixel interior match in the supplied camera file, the missing 12/12/8/12-pixel strips, and a regression that fails on dev12. The shutter fix and dev12 RAW speed changes remain. New camera edge coverage is pending owner confirmation.

The EOS M owner confirmed dev11 capture and reported more than three seconds before photo review. Dev12 retains that shutter path and reduces the registered RAW kernel's work: only necessary horizontal source bands are decoded, packed vertical sample pairs are averaged directly, and aligned Canon14 group accesses reduce memory operations. Independent reference tests check unchanged output. The [instruction-cost comparison](raw-processing-cost.md) records lower synthetic ARM cost; real-camera dev12 timing remains unconfirmed. Other camera capabilities and the capture gate's checks/deadlines are unchanged.

Dev11 addresses the owner-reported EOS M error 7 after shutter press. The pinned EOS M GUI header has `BGMT_PRESS_HALFSHUTTER` but no `BGMT_PRESS_FULLSHUTTER`; the core maps missing GUI keys to an unavailable value. Native capture now accepts the physical half-key/property as a preparation signal, retains a short release grace period for quick clicks, and refreshes a held focus latch only while valid LV continues before a capture job starts. Half-press alone never runs the RAW stage. The existing capture caller/context/readout/overlap checks and processing deadlines remain. The private two-row RAW lease is now a separate tail after the preview canvas in the same allocation, allowing preview rendering during half-press; this adds 18,480 bytes on EOS M. Release, cancellation and shutdown still retain/free the arena in order. Regression tests cover actual module dispatch and the real preview/gate/RAW path, including a photo with no full-GUI event. The owner subsequently confirmed that dev11 capture works; this does not validate other cameras or dev12 timing.

Dev10 fixes the EOS M report of `Capture stopped (code u)` on dev9 r2. The menu now shows the actual numeric capture error and a readable reason, with observer/hook detail where relevant. All numbers in this fault display use the module's bounded formatter because EOS M's Canon formatter lacks `%u`. A dedicated callback test reproduces the old output and checks all 16 displayed failures with a Canon-formatting model on the host and both ARM CPU models. The capture gate, RAW processing and capability selection are unchanged; the user's underlying stopped capture still requires the now-visible error code. Dev9 results below remain historical evidence for that version.

The goal is one module binary that can safely move between supported cameras. This candidate follows the maintainer's advice: runtime camera/firmware selection, no platform headers, no camera-dependent core struct-return ABI, and explicit refusal where no supported path exists. It does **not** establish native RAW support on every ML camera.

The `0.3.0-dev9` legacy/upstream builds are byte-identical. The [automated baseline](emulation.md#automated-universal-baseline) now runs the same actual module through every available eligible firmware bundle and records missing inputs independently. Its owned-buffer fixture checks the loaded module's 44 reflection layouts independently of Canon LiveView delivery. Dev4 checks contiguous free memory before allocating a preview frame; dev5 separates cached-image validity from current delivery eligibility. Unsupported layouts, menu/review transitions and suspended LiveView invalidate capture eligibility until a fresh accepted frame arrives. A valid shutter latch survives the subsequent Canon LV exit. Dev6 also seeds Canon's current review state during initialization and waits for each ON session's first frame before reporting preview delivery. Preserve this shared implementation; add camera-specific adapters only where generic approaches fail on evidence. The normal native-photo workflow remains EOS M only. The 70D research variant is isolated from this universal candidate.

The pinned core's `CBR_RAW_INFO_UPDATE` callback runs after `raw_info` metadata updates (`src/raw.c`, `raw_update_params_once` and `raw_lv_update`). `raw_lv_request` requests LiveView RAW, and `can_use_raw_overlays_photo` concerns access for overlays. None of these interfaces currently supplies Mirror with a documented writable interval before Canon's native-photo compression. They are candidates for generic access/geometry, not evidence that overwriting a photo buffer inside a metadata callback is valid. Continue investigating shared capture integration before extending the runtime hook table to more models.

The public 0.2.0 downloads and their archived source are unchanged. All new binaries require camera testing, including the refactored EOS M backend.

The [RAW color-plane registration investigation](cfa-registration.md) reproduces a spatial error in both 0.2.0 and dev6 source using an independent affine-ramp test. Dev7 replaces cell reversal with same-CFA-plane interpolation and borrows two packed rows from the private preview canvas before shutter-driven LV exit. The new primitive passes an independent out-of-place reference across 3,432 cases on the host and both ARM emulator CPU models. The native gate also compares full-size EOS M and research-only 70D outputs across all 44 layouts with an interpolation reference. The original camera CR2 is still missing, and no hardware fix is claimed.

## Current capabilities

| Camera | Canon firmware | Candidate capability | Hardware evidence |
|---|---|---|---|
| Original EOS M | 2.0.2 | LiveView and native CR2 backend | 0.2.0 was camera-tested; this refactor needs retesting |
| 5D Mark II | 2.1.2 | LiveView preview only | Not tested |
| 5D Mark III | 1.1.3, 1.2.3 | LiveView preview only | Not tested |
| 6D | 1.1.6 | LiveView preview only | Not tested |
| 7D | 2.0.3 | LiveView preview only | Not tested |
| 50D | 1.0.9 | LiveView preview only | Not tested |
| 60D | 1.1.1 | LiveView preview only | Not tested |
| 70D | 1.1.2 | LiveView preview only | Not tested |
| 100D | 1.0.1 | LiveView preview only | Not tested |
| 550D | 1.0.9 | LiveView preview only | Not tested |
| 600D | 1.0.2 | LiveView preview only | Not tested |
| 650D | 1.0.4 | LiveView preview only | Not tested |
| 700D | 1.1.5 | LiveView preview only | Not tested |
| 1100D | 1.0.5 | LiveView preview only, 720×240 | Not tested |
| Other models or firmware | Any | Initialization refused | No support claimed |

The project targets the 21 models in `targets/official-cameras.json`, matching the official downloads list supplied by the owner. A QEMU launcher entry alone does not add a camera to this scope. The current preview candidates are the models in that scope enabling `CONFIG_DISPLAY_FILTERS` in [upstream revision 142472e](https://github.com/reticulatedpines/magiclantern_simplified/tree/142472e95054d73640f50789ac0fd66325499d82/platform). This is a source audit, not proof of hardware operation or core-export availability. A core missing required imports refuses to load the module. Ports without ML display filters (including the newer DIGIC ports) cannot gain LiveView support just by adding their names here.

On preview-only cameras the menu explicitly says **ON - Preview only** and explains that photos stay original. The physical shutter, autofocus, SET and Play remain Canon controls. Native capture requests, hook installation, DMA inspection and sensor access are disabled without a selected native backend. Preferences still save normally.

The preview uses ML's runtime dimensions and locks them for each allocation. Only the eligible ports' native UYVY LCD layouts, 720×480 or 720×240 with a packed stride, are accepted. RCA, oversized layouts and unknown strides are rejected. A buffer-layout change, HDMI, zoom, shutdown or review state prevents further rendering to an incompatible buffer. Global Draw must be ON. Only one MAXmade effect may run; Kaleido is included in the conflict check.

## Why native RAW needs individual camera ports

ML's generic `CBR_PRE_SHOOT`, `CBR_POST_SHOOT` and `CBR_RAW_INFO_UPDATE` callbacks do not provide a writable sensor-buffer lease before Canon CR2 compression. A RAW buffer visible during quick review can be too late. Matching sensor resolution, DIGIC generation or an address in another camera's ROM is not enough to establish a safe write window.

`modules/mirror/mirror_camera.c` owns the EOS M hook words, caller/context addresses, descriptors, sensor geometry and crop. They are selected by `is_camera("EOSM", "2.0.2")`. The gate and trace also check the selected backend themselves before acting. Each hook's original instructions are checked before installation.

The old `edmac_get_info` import has been removed. Its returned structure changes on DIGIC 8+, which would create an ABI hazard. The EOS M adapter reads scalar shadow registers via core exports after verifying that the EOS M backend is selected, and copies them into a module-owned structure. It preserves the original DIGIC V signed-offset interpretation.

For a new native port:

1. Establish the exact model and firmware, safe synchronous capture window, caller/register context, sensor ownership, competing consumers and shutdown behavior on that camera.
2. Add an independently verified backend and its scalar DMA adapter. Verify instruction guards, register layout, cache aliases, memory barriers, dimensions, packing, optical-black margins and processing limits. Keep native capability absent until the adapter exists.
3. Run synthetic packed-RAW tests and compare actual original/mirrored CR2 files from the target camera. Check normal AF/shutter/review behavior, repeated single shots, cancellation and conflicts.
4. Document the actual ML build and camera-test results before promoting that profile to supported native capture.

There is no automatic ROM scanning or fallback to EOS M addresses.

The [70D native-port research](../targets/70D.112/README.md) demonstrates why a matching processor and ROM signature are insufficient: the corresponding PreDevelop job field is at `0xac`, while EOS M uses `0xb4`. `stage_job_offset` is therefore part of the runtime backend. The normal build keeps 70D native capture disabled. An explicit `--research-70d --upstream` build enables the backend only in a separate, unshipped main-module variant. The [dev9 experiment](../targets/70D.112/emulator-research.md#dev9-main-module-saved-raw-capture) verifies all 20.6 million pixels of one Canon-saved mirrored CR2 through that variant, using synthetic inputs, a software shutter and a completion-only patched emulator. Ordinary Canon LiveView/physical-key integration and hardware operation remain unverified.

## Module hierarchy and shared code

The builder stages a self-contained `modules/mirror/` inside its ML checkout: common sources go into `shared/`, and the format/review helpers into `engine/`. The module Makefile only references those local files and ML's generic `src` headers. The builder checks compiler dependency files and fails if any `platform/` header is included. It builds as ARMv5TE using upstream's module rules.

The pinned ML loader requires an **exact API major match** (`src/module.c`, the `api_major == MODULE_MAJOR` check); only minor versions are backward compatible. One file therefore cannot load on both API-7 and API-8 cores under that loader. The main API-8 binary covers the current shared implementation; the API-7 preview variant is the second necessary binary from the same source tree. Camera/firmware selection stays at runtime within each variant. Renaming a module or editing its version tag would not establish compatibility.

For an initial Mirror Worlds contribution, the common sources remain privately namespaced in the module. This also keeps the older EOS M loader usable. A hidden automatically loaded library shared with Kaleido is a separate possible upstream change; it is not introduced here because older loaders lack that mechanism and this repository contains no Kaleido module to validate against. The current candidate does not depend on another MAXmade `.mo` file.

After `python tools/build_module.py --module mirror --upstream`, the staged source is in `.cache/ml-upstream/modules/mirror/`. Its `shared/` and `engine/` folders must accompany it when copying it into a clean upstream tree; exclude its generated `build/` folder.

`python -m tools.export_upstream_module` exports the verified source as a self-contained module folder and Git patch, then applies/builds it in a clean pinned upstream tree. The dev9 review bundle contains 39 source files and reproduces the candidate's exact module hash. The [handoff guide](upstream-contribution.md) records build steps and compatibility limits.

## Validation and camera testing

The [emulator guide](emulation.md) includes the tested WSL fallback and per-camera source-core audit. `python -m tools.audit_camera_cores --runtime wsl` checks actual core exports and 23 used shared-struct fields against the same module bytes. Its results feed the generated compatibility matrix; build failures remain explicit. A [separate cached-distribution audit](emulation.md#cached-distribution-audit) checks exact archive exports and peer API metadata. The cached community 7D build has API 7 peers and four missing imports, so it is incompatible with the current API 8 candidate. A [separate API-7 preview experiment](api7-preview-test.md) now builds from the same renderer/source tree with native hook code excluded; its 49 imports resolve and 23 SDK fields match, but it has no actual load or camera validation. Other matching archives still need core-layout and runtime checks. These checks do not replace actual module initialization, capture integration or camera tests.

Run:

```sh
python scripts/test_portability.py
python scripts/test_portability.py --sanitize
python tools/build_module.py --module mirror --upstream
python tools/build_module.py --module mirror
python scripts/verify_release.py
```

Host tests execute the actual selection, capture gate, trace and renderer code. They check every listed preview profile and wrong firmware, no native reads/patches without a backend, ROM mismatch rejection, scalar DMA decoding, and capture-context rejection. Full-size synthetic EOS M and research 70D hook transport checks all 44 layouts per backend against an independent pixel oracle, including unchanged margins. Sixteen additional 70D cases reject invalid capture layouts, absent latches, competing consumers, cancellation, shutdown, unavailable workspace and rapid OFF/ON before sensor mutation. Preview checks all 44 layouts at 720×480 and 720×240, input preservation, output bounds, mode changes, Canon control passthrough and allocation cleanup.

These checks do not emulate Canon scheduling or establish hardware safety/timing on a new camera. Before using a candidate for photography, test the relevant camera/build with the module initially OFF. Verify the menu capability indication, LiveView and normal unmodified capture on preview-only models. Retest EOS M mirrored CR2 output before replacing the existing 0.2.0 installation. Do not dynamically unload a module that has installed native hooks.

The [ROM-free ARM binary fixture](emulation.md#automated-universal-baseline) additionally executes the existing API-8/API-7 `.mo` files across all 15 profile inputs on both supported CPU models, without recompiling their source. Its 60 passing profile runs cover actual compiled menu/property/renderer/lifecycle code against a synthetic SDK. The API-7 variant exposes no native backend, including for EOS M. This adds binary-level regression evidence while leaving installed-core, firmware-loader and camera validation separate.
