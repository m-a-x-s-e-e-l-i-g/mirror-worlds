# Emulator and camera-port validation

The supported scope is `targets/official-cameras.json`: 21 official models reviewed, narrowed to the 14 models whose audited ML source enables LiveView display filters. There are 15 firmware profiles because 5D Mark III has two. The priority is one universal module with shared functionality and minimal runtime adapters. Models without display filters are excluded. Native capture outside EOS M remains incomplete; generic core APIs must be evaluated before adding more model-specific code. Camera-owner validation remains required.

## Automated universal baseline

The normal `0.3.0-dev9` builds against legacy and upstream ML produce the same module SHA-256: `fb09df85a94ffe274a0f70d2415193a9971ec08b4efaeb4174d2950c5830c449`. That one binary passes the 61-import and 23-field ABI audit on 14 source-built firmware cores. The 7D source core does not build. These checks do not prove runtime compatibility with arbitrary installed ML builds.

Run from the repository on Windows with WSL Ubuntu:

```sh
python -m tools.audit_camera_cores --runtime wsl --reuse-cores
python -m tools.build_qemu_control
python -m tools.run_camera_matrix --host-tests --module-fixtures
```

Omit `--reuse-cores` when the pinned ML source changes or cores have not been built. The reuse mode verifies existing core/export/build-log hashes and rechecks the current module; it cannot turn a previous failed core build into a pass. The runner uses a new timestamped directory under `build/compatibility/`, or an explicitly unused `--output` path. `--plan-only` lists input readiness without starting QEMU.

The ROM-free [actual-module ARM fixture](../scripts/test_arm_module_binary.py) links the existing `.mo` files into semihosting executables on `arm946-eos` and `arm946-eos5`. It recompiles the synthetic SDK wrapper, not the module. Both the unchanged API-8 dev9 candidate and the separately built API-7 dev9 preview variant pass all 15 profiles on both CPUs: **60 profile runs**. It checks startup with an existing review state, menu/property callback metadata, preparing/ready status, UYVY reflection bytes including reversed luma order, input/guard preservation, review invalidation, OFF/ON, preferences and cleanup. The 1100D uses 720×240. Unknown EOS M firmware is refused. A deliberately corrupted output fails the oracle. The snapshot-backed result is `build/compatibility/dev9-arm-binary-lifecycle-v2/results.json`.

This fixture provides a synthetic SDK and bounded task stepping. Its API-8 EOS M hook guards/patch calls are stubs; sensor/task/DMA reads are forbidden. Its API-7 menu formatter uses an English formatting shim. It establishes neither a Canon boot nor the ML dynamic loader, real installed-core layout, actual display delivery or native RAW timing. API-7 hardware/export eligibility remains limited to the separately audited 7D archive. No ROM inputs are required:

```powershell
python scripts/test_arm_module_binary.py --api7-build build/research/api7-preview/dev9-binary-matrix --output build/compatibility/NEW-ARM-BINARY-FIXTURE
```

Generate the API-7 build first with `python -m tools.build_api7_preview --output build/research/api7-preview/NEW-API7-BUILD` when needed, and pass that exact directory. Add `--arm-binary-report build/compatibility/dev9-arm-binary-lifecycle-v2/results.json` to the matrix command to attach these hash-checked synthetic observations without changing firmware boot/module-load or hardware status.

The runner enumerates every eligible firmware. Each usable input bundle gets a private SD/CF copy and fresh OFF preferences. It verifies the boot image and symbol file extracted from the card against the matching ELF cohort, checks the actual core's imports/layout, installs the same module bytes, and loads the module through ML's normal loader. The unshipped generic `mxctl` helper invokes the normal ML menu API from a DryOS task. QMP presses LiveView; GDB observes initialization, preview counters, display buffers, capture-gate state, ON/OFF results, memory cleanup and crash messages. No synthetic frame or forced Canon/module state is counted as displayed preview evidence. A failed observation re-polls the existing VM, and QMP normally stops each owned process. Original cards/ROMs and released artifacts are preserved.

`results.json` and `results.md` separate source ABI, initialization, LiveView property, delivered frames, RAW status and input/emulator failures. Missing and invalid bundles are recorded independently so other profiles continue. RAW remains `not_run_no_delivered_preview` where frames are unavailable. The pipeline does not currently establish a complete normal-shutter/CR2 workflow on additional models. `--host-tests` additionally runs the actual shared-code sanitizers and independent preview oracles on both emulated DIGIC 4/5 CPU types; those fixtures are labelled separately from Canon firmware runs. Sources and measured artifacts are hash-linked in the result directory.

`--module-fixtures` additionally feeds owned synthetic UYVY buffers through the actual loaded shared `mirror.mo`, including its real cache operations and core imports. It checks all bytes for 44 mirror layouts, verifies unchanged input/guards, and runs a deliberately corrupted output case which the checker must reject. Canon's earlier frame count remains unchanged in the report; fixture-induced frame counts are recorded separately. This helper may temporarily borrow photo memory through the core allocator, frees the lease before OFF/cleanup, and never requests a shutter release. It is unshipped and is not a production preview allocator or evidence of RAW ownership.

Dev7 also exercises the loaded module's registered Canon14 primitive through actual cross-module imports. Two input patterns cover 44 layouts each: 88 tiny-frame cases and 67,584 independently checked samples, with guards and deliberate corruption. `build/compatibility/dev7-registered-matrix-v1/results.json` records those tests passing on 70D alongside all 44 preview layouts, three delivery checks, corruption rejection, ON/OFF cleanup and normal QMP shutdown. Canon LiveView delivery remains zero, and 14 other firmware profiles lack ROMs. The separate sanitizer receipt `build/registered-raw/dev7-capture-integration/results.json` freezes the host binaries, source and logs for all 44 full-size EOS M layouts, all 44 research-only 70D layouts, and preview-workspace lifecycle tests. These tests establish neither physical-camera capture timing nor the cause/fix of the supplied camera JPEG.

Dev8 preserves a held shot's cancellation across rapid OFF/ON and connects that cancellation to the RAW primitive's final pre-write check. `build/registered-raw/dev8-capture-integration/results.json` freezes the full sanitizer rerun, including preflight cancellation, completion after the first write, workspace retention during attempted teardown, and armed/held shutdown. `build/compatibility/dev8-cancellation-matrix-v1/results.json` records actual dev8 initialization, all 44 preview and 88 small RAW fixtures, corruption rejection and OFF cleanup on the available 70D emulator. Canon frame delivery remains unavailable; native 70D capture remains disabled in the normal module.

Dev9 [reduces the registered RAW kernel's instruction cost](raw-processing-cost.md) using packed eight-sample groups and one decoded horizontal source row inside the existing two-row workspace. The frozen CPU/pixel result is `build/registered-raw/grouped-v3/results.json`; the full-size host/capture receipt is `build/registered-raw/dev9-capture-integration/results.json`. The loaded-module run `build/compatibility/dev9-grouped-matrix-v1/results.json` passes the same 44 preview layouts, 88 small RAW cases, corruption checks and OFF cleanup. No new camera backend or physical-camera timing claim is introduced.

The first DMA-buffer fixture in `build/compatibility/dev3-module-fixtures` asserted in Canon's allocator on a fragmented block request; that failure remains recorded. The CPU-only attempt refused because the available CPU heap was only 313,792 bytes. The temporary owned-buffer lease in `build/compatibility/dev4-module-fixtures-v3` then passed all 44 layouts (30,412,800 output bytes), rejected a one-byte corruption, released the lease and completed OFF cleanup with no assert/unmapped-read observations. This is actual-module synthetic rendering evidence, distinct from the still-missing Canon LiveView stream.

The same investigation exposed a shared production allocation weakness: checking total free space alone cannot establish that one contiguous frame block exists. `gl_display_alloc` now uses the core's exported `GetSizeOfMaxRegion`, with the same 1 KiB headroom as pinned `mem.c`, before calling the private allocator. It retains the original 1.5 MiB DMA reserve and never falls back to photo/SRM memory. The new API resolves on the installed EOS M core and every successfully audited firmware core. Sanitizer tests explicitly reject a pool with ample total space but a too-small contiguous region. This snapshot check cannot make a later allocation atomic.

The core builder now reads an existing `Makefile.platform.default` when a legacy port supplies one. For 7D this advances past the missing build configuration without inventing firmware addresses. Compilation then fails on the port's missing `MALLOC_STRUCT_ADDR` and malloc structure definition. That upstream integration issue remains isolated; it does not stop checks on other profiles.

Dev5 fixes stale delivery eligibility. The dev4 host regression returns an old frame immediately after unsupported geometry is selected; the actual dev4 `.mo` also fails the new review-transition fixture with result `-19` after all 44 pixel layouts pass (`build/compatibility/dev4-delivery-regression`). A private `delivery_valid` flag now expires independently of the cached canvas. Mode restoration/query alone cannot revive it: only a new accepted render can. Canvas/history contents remain available to rendering. The host suite checks nine invalidation/recovery cases at each LCD height, and combines the real preview getter, shutter gate and full RAW transform to verify both rejection of stale latches and completion of an already valid EOS M latch after Canon LV exit. The dev5 compiled-module fixture passes the three review/fresh-delivery assertions too (`build/compatibility/dev5-delivery-regression`). These are SDK/emulator fixtures, not physical-camera timing proof.

Dev6 fixes shared startup and status behavior. Pinned ML `module.c` initializes a module before registering its property handlers. The previous entry point unconditionally seeded GUI state 0, allowing the real shared filter to report ready while Canon's known initial review state was 1 (`.cache/dev5-startup-review-before.log`). It now seeds from the exported `gui_state`. A second fixture reproduces the premature preview label before any accepted frame (`.cache/dev5-first-frame-status-before.log`). The shared frame counter is cumulative, so an intermediate fix also failed OFF/ON restart (`.cache/dev6-restart-status-before.log`). The final code remembers the frame baseline at each start. No public structure layout or camera-specific backend changes.

`tests/module_lifecycle.c` runs the actual module entry points, property callbacks, renderer, runtime selector and two-slot preference code with a simulated SDK. It covers 15 firmware profiles, initial states 0/1/3/12, both LCD heights, fresh frames after restart, valid control combinations, write retry, desired-ON persistence through shutdown, unsupported firmware and both task-creation failure values. The default sanitizer suite includes it. The unshipped QEMU helper additionally reads the real menu update callback through ML's serialized menu API, recording whether an initialized zero-frame module says Preparing. The final matrix is `build/compatibility/dev6-final-matrix-v2/results.json`; current sanitizer output is `.cache/dev6-final-portability.log`. These host tests remain distinct from actual firmware initialization and camera testing.

The first final dev6 matrix stopped before the asynchronous loader populated `module_list`, despite no loader error or Canon assert (`build/compatibility/dev6-final-matrix`). The runner previously misclassified this as failed initialization. Startup analysis now distinguishes pending observations from explicit loader errors and keeps polling the same VM. Unit tests cover empty/intermediate module lists. A pending observation that reaches its deadline is reported as an observation timeout, not a loader failure. The final v2 run uses this correction; it does not restart a VM when an observation is incomplete.

Local input bundles use `.cache/qemu-inputs/MODEL.FIRMWARE.json`. A bundle contains `target`, `canon_id`, `symbol_name`, and `artifacts` entries for `core`, `autoexec`, `symbols`, `sd`, and `cf`. Each artifact has a workspace-relative `path` and a SHA-256. Build `autoexec.bin`, exports and the matching ELF together. ROMs remain in the firmware-separated directories described below. No proprietary dump is included in a candidate ZIP.

The available 70D bundle passes initialization, menu ON/OFF and allocation cleanup with no assert/unmapped-read observations. Canon reports LiveView active, but its image buffer remains unavailable and zero frames are delivered. Other eligible firmware runs are explicitly skipped for missing ROMs. Continue shared API/ABI and host work while these emulator inputs are unavailable; avoid extending the isolated 70D investigation into the main compatibility baseline.

A separate [dev6 main-module capture fixture](../targets/70D.112/emulator-research.md#dev6-main-module-expired-latch-fixture) now connects an owned synthetic preview and software full-press to Canon's real capture stage using the research backend. The main gate refuses the delayed latch before mutation, and all 20,646,144 pixels in Canon's saved CR2 remain original. That negative result is not successful native mirroring; the normal candidate still keeps 70D native capture disabled.

## Cached distribution audit

Source-built cores and distributed builds are separate evidence. Run the static archive audit with a local download receipt:

```sh
python -m tools.audit_distributions --manifest targets/distribution-inputs.json
python -m tools.camera_matrix --runtime wsl --automation-report build/compatibility/dev5-universal-full/results.json --distribution-report build/distribution-audit/NEW-AUDIT/results.json
```

Use the fresh output directory printed by the audit in place of `NEW-AUDIT`. The versioned input receipt records each exact camera/firmware, provenance kind, source URL, local ZIP path and SHA-256; community inputs additionally have pinned Git blob hashes and sizes. Obtain the archives at those paths separately; an absent file is recorded independently and does not stop other targets. This command reads local archives without installing or executing them. It checks archive integrity, exact target export tables, candidate imports and symbol-addressed peer module API bytes. It rejects duplicate paths, wrong targets and changed inputs. The 1100D export filename `t3_105.sym` is an explicit alias from the pinned platform Makefile. Existing output directories cannot be overwritten. The report snapshots the candidate, export tables, peer metadata, input receipt and relevant audit sources with artifact hashes. Matrix attachment rechecks these hashes and current candidate/scope before adding a separate distribution column.

The October 28 audit of the unchanged dev5 binary covers 15 cached archives: one previously verified official EOS M build and 14 community distributions, one per eligible model. Fresh requests to the official downloads server returned HTTP 403. The community inputs come from [magiclantern-zh at dc3d012a](https://github.com/ryulin456/magiclantern-zh/tree/dc3d012aff3ddc0e07df3ceafb9b95dbfdf56f12), retained only as offline audit inputs. They are not recommended replacements for official ML builds. The selected 7D archive is the corrected r2 package; the mislabeled older 5D3 experimental 1.1.3 archive is excluded. No 5D3 1.1.3 distribution was audited.

| Input class | Imports and peer API metadata match | Limitation |
|---|---|---|
| Official EOS M 2025-06-20 | 1 of 1 archive | Already cached; no new official builds obtained |
| Community builds | 13 of 14 archives | 7D 2.0.3 differs |
| 5D3 1.1.3 | Not checked | No suitable archive in this input set |

All 61 imports resolve on the 14 matching archives; their peer modules declare API 8.0. The cached 7D 2020Dec28 build's 19 peer modules instead declare API 7.0, while Mirror Worlds declares API 8.0. Its export table also lacks `get_current_task_id`, `patch_hook_function`, `read_value` and `sync_caches`. The first three belong to the native capture gate/trace; cache synchronization is also used by shared preview. Removing only optional native imports would therefore leave both an essential preview dependency and an API mismatch. Do not change the metadata version byte or invent export addresses to make this build load. A compatible 7D core or a separately audited API-7 variant remains necessary.

The frozen result using the versioned receipt is `build/distribution-audit/dev5-distributed-baseline-v3/results.json`. These checks do not establish the distributed cores' shared-structure layouts, loader behavior, initialization, Canon LiveView delivery, RAW ownership or physical-camera compatibility. The dev5 candidate ZIP remains unchanged; this newer audit is a separate supplement.

### API-7 preview variant

`python -m tools.build_api7_preview` now builds an isolated variant from the same source tree using the real historical API-7 module SDK, pinned to the distribution repository above. It downloads only missing hash-verified SDK files and executes no downloaded Makefile/script. Historical `platform/all` headers are the SDK's generic module stubs, not camera-specific addresses. The SDK's inline `sync_caches` compiles into the variant; no export address is invented. A common `MIRROR_PREVIEW_ONLY` build mode excludes the native gate/trace implementations and returns no native backend on every camera. The worker accepts both historical pointer and current integer `task_create` return declarations through `uintptr_t`.

The initial result at `build/research/api7-preview/dev5-7d-candidate/results.json` records actual API 7.0 ELF metadata, 48 resolved imports against the exact cached 7D archive, and 23 module-used shared fields matching an independently compiled historical-SDK probe. The source gate test checks all 15 firmware profiles with no hardware APIs linked, including refusal of native requests on EOS M. This does not prove the shipped 7D core's full layout, actual module loading or preview delivery. That experiment preserved the normal dev5 API-8 binary. The updated dev6 API-7 candidate is at `build/research/api7-preview/dev6-7d-candidate-v2/`; reading Canon's initial GUI state adds one available export, so its 49 imports resolve against the same archive.

An explicit experimental ZIP, `MIRROR-API7-7D-PREVIEW-EXPERIMENT.zip`, sits alongside that result. It includes source, SDK provenance/license, validation receipt, file hashes and [short owner instructions](api7-preview-test.md). It contains no replacement core, emulator helper or ROM. Saved photos remain original. This variant is not substituted into the standard API-8 matrix or the main candidate ZIP. A 7D owner with an existing API-7 installation must still validate initialization, preview, ON/OFF cleanup and normal saved photos.

## Reproduce the Linux tooling from Windows

The tested fallback is Ubuntu under WSL. Docker remains an alternative in the scripts. The emulator is the ML team's [QEMU-EOS fork](https://github.com/reticulatedpines/qemu-eos/tree/4b667a1d3c08ab7a55835d15ddbd884fa754946d/magiclantern), pinned to commit `4b667a1d3c08ab7a55835d15ddbd884fa754946d` on `qemu-eos-v4.2.1`.

Install the Linux build dependencies once inside Ubuntu:

```sh
sudo apt-get install build-essential pkg-config libglib2.0-dev libpixman-1-dev zlib1g-dev libjpeg-dev libpng-dev flex bison python3-pil mtools qemu-utils gdb-multiarch xz-utils gcc-arm-none-eabi libnewlib-arm-none-eabi python3-docutils zip
```

From the repository directory in PowerShell:

```sh
python tools/build_qemu_eos.py --runtime wsl
python tools/build_module.py --module mirror --upstream --runtime wsl
python tools/build_module.py --module mirror --runtime wsl
python scripts/test_portability.py --runtime wsl --sanitize
python scripts/test_arm_preview.py --runtime wsl
python -m tools.audit_camera_cores --runtime wsl
python tools/camera_matrix.py --runtime wsl
```

Existing Windows-mounted module build directories created by Docker may require `--wsl-user root` for those two module commands. Fresh native Linux staging for the core audit uses the normal WSL user's cache. No global Git ownership exception is needed. The core audit extracts a Git archive of the pinned revision, rather than building a mutable source copy; it does not require Canon ROMs. It builds with `FATAL_WARNINGS=n` for the installed GCC 13 toolchain and records build failures.

The module builder also keeps `mirror.debug.o`. Stripping this object must reproduce `mirror.mo` byte for byte before its DWARF types are accepted as evidence. The core audit compares the candidate's 60 imports and the sizes/used fields of six shared structs: LCD layout, display-filter buffers, lens state, config entries, menu entries and menu display data. It checks 23 fields, including the selected-menu bitfield. It does not assume that resolving a symbol name proves its ABI.

Results go to `build/qemu-eos/`, `build/tests/` and `build/camera-cores/`. The per-core build logs and symbol tables identify the exact locally built sources, not whatever ML version is installed on an owner's camera. The pinned `7D.203` Makefile lacks `MAIN_FIRMWARE_ADDR`, so its source-core check currently fails; adding an invented value would not establish the correct dual-processor build.

## Canon firmware inputs

Use the expected filenames and sizes in `build/qemu-eos/camera-matrix.json`. Keep inputs separated by model and firmware, for example:

```text
.cache/roms/EOSM/202/ROM1.BIN
.cache/roms/EOSM/202/SFDATA.BIN
```

EOS M needs a 16 MiB ROM1 dump and 8 MiB serial-flash dump; its QEMU descriptor does not require ROM0. A Canon updater `.FIR`, ML ZIP, or a different camera's dump does not fill those requirements. [ML's serial-flash dumper](https://github.com/reticulatedpines/magiclantern_simplified/tree/142472e95054d73640f50789ac0fd66325499d82/modules/dev_tools/sf_dump) is the existing source for acquiring serial-flash data from an owner-operated camera. Other profiles' sizes come from compiling QEMU's actual model descriptors with their inherited defaults.

ROM directories and emulator scratch files stay in ignored local storage and are excluded from candidate packages. The matrix rejects missing, mis-sized and empty/marker placeholder files; a nonempty file with the correct length still needs model/firmware provenance. It never promotes an input hash to a successful boot or module-load result.

## Observed results and limits

- The pinned emulator and ML plugin built successfully under WSL.
- The actual ARM preview renderer passed all 44 layouts at 720×480 and 720×240 on both QEMU's DIGIC 4 and DIGIC 5 CPU models. This uses a synthetic semihosted test executable on a generic board; no Canon firmware or module loader participates.
- An exploratory EOS M run used the owner's genuine ROM1 backup, the hash-verified official 2025-06-20 ML core archive, a virtual SD card containing the candidate, and explicitly experimental empty serial-flash data. It read `AUTOEXEC.BIN`, jumped into it, and reached Canon's `K331 ICU Firmware Version 2.0.2` startup. It then logged missing property packages and asserted in `RscMgr.c`, startup task, line 239. The screen remained blank apart from a red mark. A successful Canon/ML startup, module initialization and capture were not verified.
- The experiment's generated flash file was removed from the normal ROM input directory. The genuine EOS M serial-flash input remains missing. A public development repository's EOS M flash file was also inspected and rejected: it was a short text marker followed by zeros, and its ROM1 file was truncated. Neither is a usable camera dump.
- A separate **70D 1.1.2** input set from [this pinned development repository snapshot](https://github.com/peva3/magiclantern_70D/tree/302806f5fb58a52ce458f65fb9612430ea0cf589/roms/70D) contains executable ARM code at the pinned ML stub addresses. Canon startup identifies `K325 ICU Firmware Version 1.1.2 (8.1.6)` and completes initialization. Its 16 MiB flash container was retained unchanged in quarantine; an exact first-8-MiB region was extracted for QEMU because Canon's own `InstallSerialFlash` reports `0x800000`, matching QEMU. The extracted region's SHA256 is `6a4a3824cad4661aa4b689b0287e150547816d685ceb94a7f97a4994512b1672`. No padding or generated flash bytes were used. The external owner's hardware/provenance claims remain independently unverified.
- **Mirror Worlds initialized successfully in that 70D emulator run.** GDB reads `ml_started=1`; the core's module table identifies `mirror`, API 8.0.0, enabled/valid, status `OK`, error zero, and the `mirror_worker` task exists. The exact candidate module is unchanged from the packaged build. LiveView remained OFF, and the screen remained blank apart from a red mark: neither preview rendering nor native RAW capture is verified. The native 70D capture backend is still absent.

The exploratory logs are local at `.cache/eosm-probe/serial.log` and `qemu.log`; their associated synthetic flash remains quarantined there. Do not repeat that experiment as a supported firmware test or replace missing data with padding. A successful firmware test must use authenticated matching inputs, record their hashes, confirm the module's own initialization, exercise preview/capture paths, and retain its actual outputs. Hardware testing is still required even after an emulator test passes.

The current 70D receipt is `build/qemu-eos/70D.112-dev2-observation.json`, with hash-linked serial/GDB logs, core ELF, `autoexec.bin` and candidate module. The earlier `70D.112-observation.json` remains historical evidence for the previous candidate. The matrix verifies those artifact hashes before attaching an observation. Its two kinds of evidence stay separate: source-core checks and measured emulator initialization. An older observation is retained as historical evidence if the current candidate changes.

A separate patched-emulator experiment now saves a Canon 70D CR2 whose 20,646,144 RAW pixels match a generated sensor ROI through independent LibRaw decoding. The preview and thumbnail are synthetic flat gray. Its receipt is `build/qemu-eos-70d-cr2/70D.112-cr2-observation.json`; the matrix validates all linked hashes and reports this in a separate generated-frame category. This does not promote the module's 70D native backend or hardware status. See [the experiment and reproduction commands](../targets/70D.112/emulator-research.md#canon-cr2-output-and-slice-order).

The later [isolated ARM probe](../targets/70D.112/emulator-research.md#isolated-arm-mirror-probe) also verifies correctly mirrored Canon CR2s for two edge settings, including consecutive shots in one boot. The matrix labels that as probe evidence. Its snapshot-backed receipt is `build/70d-native-probe/70D.112-probe-observation.json`; no research probe binary is shipped in normal camera candidates.

The [dev9 research main-module capture](../targets/70D.112/emulator-research.md#dev9-main-module-saved-raw-capture) goes further: the actual isolated `mirror.mo` gate transforms and saves one Right/Half Canon CR2, with all 20,646,144 RAW pixels independently verified and optical-black margins unchanged. A guarded, completion-only FB/FC emulator model removes the earlier preprocessing waits without extending module deadlines. Synthetic preview/sensor input and a software shutter are explicit limitations; real Canon LiveView, physical keys, hardware timing and other settings remain unverified. The normal universal module keeps 70D native disabled. Add `--main-capture-report build/research/mirror-70D.112-dev9-flow/70D.112-main-registered-receipt.json` when generating the matrix to include this separate, hash-checked research category.

The [repeatable native regression](../targets/70D.112/emulator-research.md#repeated-main-module-capture-regression) verifies cancellation before mutation, OFF/ON recovery and three Canon-saved CR2s with different settings in one boot. All 61,938,432 RAW pixels match an independent registered-reflection oracle; margins remain original and OFF frees the workspace. The fixture additionally uses software LV_START because Canon does not reliably return to LV in this emulator. `python -m tools.run_native_capture` runs the isolated cohort; `scripts/test_native_capture_sequence.py` independently checks its saved files. Add `--native-sequence-report build/research/native-flow-dev9-sequence-v4/70D.112-sequence-receipt.json` to the matrix command after freezing that receipt. This is research integration evidence, with no normal 70D native or hardware-support promotion.

The `0.3.0-dev2` candidate moves the capture-job field offset into the camera backend after static 70D analysis showed `0xac` versus EOS M's `0xb4`. The actual EOS M hook transport and all 44 full-size RAW layouts still pass the sanitizer tests, including unchanged margins. The stock 70D emulator initializes this new version too; its GDB observer now reports the loaded module's version explicitly. See [70D native research](../targets/70D.112/README.md) for the incomplete capture anchors and isolated shutter-protocol experiments. None enables a 70D RAW backend or establishes a writable sensor interval.

Keyboard navigation also reached the new candidate's actual Shoot entry and Mirror Worlds submenu in the stock emulator, showing OFF, Right, Half and Not used as the fresh defaults. The screenshot `.cache/70d-dev2/mirror-controls-verified.png` records that UI observation. This does not establish LiveView rendering or photo output. Allow guest time between keys and after menu redraws; immediate screenshots during transitions can show old or blank bitmap pages.

For repeat emulator observations, source `tools/qemu_module_state.gdb.py` in GDB after loading the **matching** core ELF and connecting to the stopped guest. It only reads core state and emits a structured marker. `tools/analyze_qemu_boot.py` checks that marker against the Canon startup log and writes the receipt; absent modules, init errors, wrong firmware and duplicate observations cannot pass. It always leaves preview/capture/hardware flags false.

Build the boot image and exports in the same Make invocation (`build/autoexec.bin build/magiclantern.sym`). ML regenerates its version object on every invocation, so an earlier ELF or symbol file can describe different addresses. Preserve the resulting ELF with the boot image. Also use a fresh virtual card for each run, or account explicitly for a previous exploratory run's `ML/MODULES/LOADING.LCK`: forced emulator exits leave that file behind, and ML deliberately skips module loading on the next boot. Clearing only that stale lock in the owned **virtual image** allowed the 70D module-load test to run; this is not an instruction to bypass a camera's crash guard.

## Candidate for camera owners

After rebuilding and refreshing the complete core audit, prepare the explicitly labelled, unpublished development package:

```sh
python tools/package_module.py --module mirror --candidate --instructions docs/candidate-test.md
```

The output is under `build/candidates/`; it includes the module, source, per-profile capability notices, exact build/import metadata and [owner test instructions](candidate-test.md). It contains no camera ROMs and does not replace the released 0.2.0 files. The packager refuses to overwrite an existing package.
