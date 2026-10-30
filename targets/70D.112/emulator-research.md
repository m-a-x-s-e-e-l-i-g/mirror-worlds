# 70D 1.1.2 experimental capture emulation

The actual `0.3.0-dev2` module loads with status `OK`. The isolated experiments save Canon CR2s containing 5568 x 3708, 14-bit RAW frames. Independent LibRaw decoding matches all 20,646,144 pixels against an independent **QEMU-generated sensor** oracle, including two mirrored shots produced by the real ARM transform in an unshipped probe. Preview/thumbnail images are synthetic flat gray. The normal module's 70D native backend, physical sensor ownership and hardware behavior remain unverified; that backend stays disabled.

This uses a separate [QEMU-EOS-Optimized checkout at `147d913f`](https://github.com/giogandola98/QEMU-EOS-Optimized/tree/147d913fa455d217190509cd8f090546149d377b) and [qemu-capready-experiment.patch](qemu-capready-experiment.patch). The standard project QEMU source and binary remain at their original pin. The fork's [capture documentation](https://github.com/giogandola98/QEMU-EOS-Optimized/blob/147d913fa455d217190509cd8f090546149d377b/docs/models/capture.md) describes its simulated sensor and compression behavior. Its completed 1100D/4000D examples do not establish 70D support.

## Firmware evidence and experiment

All firmware analysis uses ROM1 SHA-256 `3fe42299deb577b269b6901f40597a1939ac5876f22c8c3a0b6ee47219fdd42e`. `native-research.json` records the instruction guards for the packet-copy sizes.

- Event manager `0xff0f21c4` copies `payload[0x37] + 0x38` bytes for release data, and `payload[0x28] + 0x29` for after-release data. The experiment sends zero-length extensions and the normal capture path. Exposure fields and event timing remain experimental, not a hardware-captured packet.
- `scsReleaseStart` calls RAM helper `0x49348`. Its context literal at `0x49400` resolves to `0x99158`; field `+0x0c` contains release GPIO `0xc02200a8`. Canon's ROM helper at `0xff147dc8` checks mode bits `[3:2] == 1` and sets bit 1; `0xff147e0c` clears it. The generic emulator returned `1`, so Canon rejected those operations. The patch supplies initial mode/level `0x44` and retains Canon's writes.
- The driver's initialization at RAM `0x492bc` registers CAPREADY interrupt `0x51`. The experiment uses the fork's existing ordered CAPREADY scheduling on the first falling edge, rather than manually setting Canon's capture-job state.
- No 70D compression, periodic VD or Fencing completion model is supplied. The generic engine produces the sensor pattern after Canon configures the transfer. The patch's original "release events ONLY" comment distinguishes it from a full camera profile; the additional GPIO/CAPREADY fields and the inherited generated readout are experimental too.

In the observed run, EDMAC channel **0**, connection **35**, writes `9884 × 3720 = 36,768,480` bytes to `0x1ca02700`, with flags `0x20001000`. The engine reports 5648 pixels per row packed at 14 bits. **This single synthetic transfer is not approved backend geometry or proof of a writable sensor-buffer interval.** Canon subsequently works on other buffers; their ownership and relationship still need tracing.

In the GPIO/CAPREADY-only experiment, Fencing B/C operations report `NRES:0x408000` timeouts. `ShootPreDevelop` then logs `StartProcess(12360)`, `ENAV EWUp:Start(2,0)` and `DecryptPresetFlavorLuckyTable`, followed by `System/postman/postman_m.c:644`. The Eeko-start call at `0xff15c4b0` precedes the proposed stage call at `0xff15c4cc`. The following experiment models the particular missing completion instead of patching out that assertion.

## Eeko completion and observed native bindings

[qemu-eeko-color-experiment.patch](qemu-eeko-color-experiment.patch) is the full cumulative patch against the same fork commit (use it instead of the CAPREADY-only patch). The 70D code at `0xff42619c` registers callback `0xff426130`, then sends command 4, parameter `0x800` at `0xff4261c0`. The callback accepts status bytes 0 through 3 and releases a semaphore. The new profile answers only that command on the reply channel. The observed request/reply is `DSLR_COLOR_PROC 000800`, after which the proposed stage executes. **The acknowledgement does not implement the requested decryption or colour work.** All other Eeko commands remain unanswered.

Three independent first-shot runs (`70d-capture12`, `13`, `14`) reach stage `0xff361910` with r10 = `0x7c15c`, LR = `0xff15c4d0`, r0 = `0x5ca00064`, and context job `0x40e3c064` at `+0xac`. The normalized observer reports CPSR `0x60000013`. These are observations in the patched emulator, not hardware scheduling evidence. Debugger stops alter timing.

The 70D RAW compression path uses a dedicated lossless implementation (`[TTL]`, entry `0xff437a80`), whose descriptor is `0xc1770`. At source setup `0xff437d58`, the measured input is 5568 x 3708 at 14 bits, source `0x5ca00064`, offset `0x1a932`, and no second source. The pointer matches the one seen at the stage. In the completion-only experiment, output connection 45 returned placeholder data repeatedly. The following JP57 experiment replaces those bytes; the earlier virtual DCIM directories from runs 12/13 contain no photos.

This is the compression window, including calibration pixels. The active image bounds and CFA origin have not been established in these coordinates. The DMA flags observed at the stage are `0x20000000`, with a completed pointer `0x1ed131e0`; the existing EOSM gate requires zero flags. Keep that gate intact until camera-specific hardware checks are established. Reusing the EOSM JPEG hook sites or geometry would miss the 70D lossless path.

`tools/qemu_70d_native.gdb.py` provides the repeatable `mirror70d-observe` command. Source it after connecting to the virtual camera and loading its matching ML ELF. It requires QEMU's remote extension and checks all three instruction guards before arming debugger breakpoints. It checks the stage caller/context and fixed lossless descriptor, prints two `MIRROR_QEMU_NATIVE=` JSON records, then stops at the lossless descriptor. It neither triggers a photo nor writes pixels or CPU registers. Trigger the virtual release separately, then continue. Both the real emulator integration and refusal to arm without a remote target were checked.

The hash-linked receipt is `build/qemu-eos-70d-eeko-color/70D.112-native-stage-observation.json`. It binds the emulator, plugin, cumulative patch, tested observer, module/core cohort and logs. The actual module version was checked before the release, and the virtual SD module was byte-compared with the built module. Runs 12/13 used prototype observers; run 14 validated the tracked observer and source-pointer equality. All were explicitly stopped through QMP.

## JP57 lossless output and pixel verification

[qemu-jp57-experiment.patch](qemu-jp57-experiment.patch) is the full cumulative patch against the same fork commit. Apply this patch alone for the latest experiment. It includes the standalone encoder and isolated adapter from `qemu/`, plus the earlier GPIO/Eeko changes. It does not alter the default project emulator or any camera module.

Canon programs JP57 at `0xc0e20000`, precision/component register `0x84 = 0x20e`, and frame register `0x80 = 0x0e7c0ae0` (2784 samples per component, 3708 rows). Canon starts EDMAC channel 8 itself, sending **36,130,752 bytes** on connection 1. Its DMA layout supplies two packed 14-bit planes, each covering one half of the compression window. The original adapter interleaved matching left/right pixels into two JPEG components and supplied **19,738,944 bytes** to output connection 45. That standalone stream decoded correctly, but the later CR2 test exposed incorrect slice ordering; the CR2 experiment below supersedes that adapter. Output waits for input; consumed connection data is released for future transfers.

The lossless reference encoder implements SOF3 with predictor 1 from [ITU T.81 Annex H](https://www.w3.org/Graphics/JPEG/itu-t81.pdf), two components and a fixed Huffman table. It preserves pixel values; it does not reproduce Canon's compression ratio or exact byte stream. Inputs, dimensions, allocation size and 14-bit range are bounded. Unsupported configurations are not modeled. Mode 7 initialization completes separately from a mode 2 image encode.

The completion interrupt is **0xa3**, registered by the 70D firmware at `0xff2bddd4`. The final run logs `[TTL] JpCoreCompleteCBR(0x12d3140)` and `Read1CompleteCBR`; the reported size is exactly the reference stream length. Completion is ordered after the modeled output transfer using emulator steps. These are not physical-time measurements.

Run the committed verification with:

```text
python scripts/test_qemu_lossless.py --runtime wsl --qemu-run .cache/70d-capture20
```

Host Python needs `numpy` and `rawpy`; Linux needs `gcc`. Without `--qemu-run`, the command tests generated fixtures without Canon ROMs. The C encoder runs with AddressSanitizer and UndefinedBehaviorSanitizer. The checks reject invalid dimensions/samples, then decode extremes, flat data, a ramp, seeded random pixels, and a full 5568 x 3708 frame through independent LibRaw. The QEMU check additionally decodes its actual output and compares all pixels against the exported input and a separately generated sensor ROI. It checks the two-plane layout and crop at sensor x = 72, y = 10; that crop is the compression window, **not** approved active-image or CFA bounds.

The final source/binary and hash-linked receipt are under `build/qemu-eos-70d-jp57-final/`. The test report is `build/tests/qemu-lossless14/results.json`; the final virtual-camera run is `.cache/70d-capture20/`. Its inspected DCIM directories contain no photo. Remaining Eeko messages include the LCD/development requests `SS_PROC 0xb00/0xb01`; completed CR2 writing and pixel order in Canon's CR2 container are still unverified.

Earlier prototypes are retained as failed research: run 16 waited for an unmodeled initialization status; run 17 started an input read prematurely, after which Canon started another, causing invalid reads and a stuck emulator. QMP and TERM did not stop that process, so that owned emulator was killed. The final implementation waits for Canon's own input DMA and completes normal QMP shutdown. Do not use the earlier codec/codec2 binaries as a working model.

## Reproduce the build

Use a dedicated Linux checkout of the fork at the exact commit above. Apply the patch with `git apply --check` followed by `git apply`; it modifies only the emulator's capture profile/data. Build ARM softmmu with plugins using `tools/build_qemu_linux.sh`, passing that separate source directory and separate build/output directories. Do not replace the standard `build/qemu-eos` output.

Boot the identified 70D ROM0, ROM1 and 8 MiB serial flash with `-M '70D,firmware=112;boot=1'`. Use private copies of virtual SD/CF images containing the matching 70D ML core, exports, fonts, current `mirror.mo`, and enable file. Clear only a stale ML module-loading lock in the private copied image when needed. Use a coherent core ELF, `autoexec.bin` and symbol-file cohort built together.

The local experiment uses an unshipped `qprobe` DryOS task to call Canon's normal `Release` procedure. GDB queues its mailbox request only after confirming the research module loaded with status `OK`. `mirror.mo` is byte-compared with the copy extracted from the virtual SD before starting. For full firmware logging add `-d mpu,guest_errors,debugmsg` and `-plugin OUTPUT/plugins/libmagiclantern.so,arg=debugmsg_addr=0x6904`; `QEMU_EOS_CAPTURE_TRACE=2` logs GPIO writes. Quit through QMP and wait for process completion before examining or reusing the virtual images.

Local inputs and scripts are in `.cache/70d-capture9/` (release events only), `.cache/70d-capture10/` (same with firmware logging), `.cache/70d-capture11/` (GPIO/CAPREADY), `.cache/start_70d_interactive.py`, `.cache/queue_70d_release.gdb.py`, and `.cache/prepare_70d_capready.py`. These contain no distributable camera build. The hash-linked receipt is `build/qemu-eos-70d-capready/70D.112-capture-observation.json`; it includes the exact emulator, plugin, patch, module, coherent core cohort and logs. All three runs were explicitly stopped; no camera or physical card was accessed.

## Canon CR2 output and slice order

The latest cumulative patch is [qemu-cr2-experiment.patch](qemu-cr2-experiment.patch), applied alone against the same fork pin. It includes the corrected JP57 adapter, synthetic preview/thumbnail replies in [qemu/eeko_lcd_research.inc.c](qemu/eeko_lcd_research.inc.c), and the missing output-DMA pop completion. Earlier patches and receipts remain historical. The previous JP57-only patch contains the earlier adapter; current `qemu/jp57_research.c` has the slice correction.

The ROM-derived main/Eeko callbacks and observed parameter layouts are recorded in [lcd-research.json](lcd-research.json). Main CPU addresses are executable ARM locations; Eeko anchors are ROM file addresses for static Thumb disassembly, not asserted runtime locations.

- `SS_PROC 0xb00` supplies a configuration box and eight output chunks. `0xb01` starts the display JPEG path; the reply is `0xb03` with a shared three-word result `{JPEG byte count, status, reserved}`. Main callback `0xff41e9fc` reads the first two words and calls `0xff16c7ac`. The model fills Canon's allocated chunks with a 5472 x 3648 flat-gray JPEG and returns 117,111 bytes. It validates the observed mode, count, memory bounds and nonoverlapping chunks. It does not develop RAW or produce Canon colour.
- `0xc00` configures thumbnail DMA handles; `0xc01` supplies parameters and one 65,536-byte output chunk. `0xc03` starts processing and receives reply `0xc01` with the same result shape. The model writes a 160 x 120 flat-gray placeholder JPEG (260 bytes). Main callback `0xff41e04c` consumes the length/status; Canon embeds a decodable thumbnail. The display/YUV processing is not emulated.
- After lossless compression, Canon's `PopEDmacForMemorySuite` at `0xff641e84` calls RAM `0x384e8`, which sets the output flags' low nibble to 6. The generic model reported pop reason 4 when polled, but did not interrupt a stalled transfer. The experiment clears only that pending transfer and raises its completion, restricted to the 70D research profile and output connection 45. Canon then logs `Write1Complete(POP)CBR` and completes its normal file-writing path.

Run 22 accepted the display JPEG, then timed out in the unmodeled thumbnail path and asserted during zero-length cleanup. Run 23 completed both JPEG paths, then waited for the missing pop interrupt. Run 24 saved a 20,797,172-byte CR2, but independent decoding revealed a RAW ordering error. Its CR2 tag `0xc640 = {1, 2784, 2784}` describes two horizontal slices. The adapter must preserve the DMA sequence (all left-half rows, then all right-half rows), grouping consecutive values into JPEG components. Interleaving corresponding pixels from the two halves was wrong even though the standalone stream matched its own input.

Run 25 uses the corrected sequence and saves **20,797,364 bytes** as `IMG_0065.CR2` on the virtual SD. Its RAW strip is exactly the **19,739,136-byte** reference lossless stream. Independent LibRaw decoding verifies all **20,646,144** pixels against the separately generated sensor ROI. Pillow decodes the embedded 5472 x 3648 preview and 160 x 120 thumbnail as flat gray. No Canon assertion or invalid-memory read was observed. The VM exited normally through QMP before the card was inspected/extracted.

Reproduce validation with host Python `numpy`, `rawpy` and `Pillow`, and Linux `gcc`:

```text
python scripts/test_qemu_cr2.py --runtime wsl --qemu-run .cache/70d-capture25
python scripts/test_qemu_lossless.py --runtime wsl --qemu-run .cache/70d-capture25
```

The first command also runs the actual Eeko adapter with ASan/UBSan and an instrumented guest-memory fixture, checking chunk boundaries, malformed/overlapping/wrapped inputs, unsupported requests, reply-allocation failure, short capacity and one-shot completion. Without `--qemu-run`, it needs no ROMs and tests only that adapter. The lossless command retains support for the historical standalone runs and reads the new run's `jp57-layout.json` to distinguish slice order; a standalone DNG envelope is not Canon-container validation.

The hash-linked receipt and source manifest are under `build/qemu-eos-70d-cr2/`; the CR2 report is `build/tests/qemu-eeko-lcd/results.json`. Run data and the extracted Canon file are in `.cache/70d-capture25/`. Research images and ROMs are not included in module candidates. LibRaw reports a 5472 x 3648 crop at RAW coordinates (84, 50), a separate 5496 x 3670 visible window, and an RGGB interpretation. These are decoder/container observations, **not an approved writable RAW interval or physical CFA origin**.

The next native-port work is active image/CFA bounds and downstream ownership checks. Integration still requires verified geometry, readout completion, competing consumers, cancellation/shutdown, and original-versus-mirrored CR2 evidence before enabling a backend candidate for owner testing. The remaining eligible models retain their separate source/emulator-input requirements.

## Isolated ARM mirror probe

The new [research/m70raw.c](research/m70raw.c) is an **unshipped QEMU probe**, independent of the normal `mirror.mo`. It links the actual `fx_mirror_raw.c` and `fx_mirror_sensor.c` ARM implementations under a private namespace. Loading it installs no hooks. The QEMU-checked GDB controller explicitly arms one shot, and a DryOS task installs six guarded cache hooks while idle. Pixel writes occur in the module's stage callback, not in GDB. There are no pixel writes in its worker, file-format replacements, Canon descriptor edits or CPU-register substitutions.

[research/raw_contract.h](research/raw_contract.h) checks the 70D's exact stage caller, task mode/interrupt state, context, current capture job, LiveView/shutdown state, and a completed readout both before and after a scheduling hold. Observed DMA layout is `xa = xb = 9884`, `xn = 3719`, `yb = ya = yn = 0`, all offsets zero, flags `0x20000000`, inactive control and a completed pointer 36,768,480 bytes beyond the configured address. The readout begins one 9884-byte row after the canonical stage source. **The row count is in `xn`, not `yb`.** Run 26 deliberately records the first incorrect contract's refusal before any sampling/writes; its saved original CR2 remains pixel-identical to the sensor oracle.

The proposed full readout frame is 5648 x 3720. Canon compresses the window at readout (72, 10), size 5568 x 3708. Its CR2 crop (84, 50), size 5472 x 3648, maps to readout region `{top=60, left=156, bottom=3708, right=5628}`. The probe transforms only that region in complete Bayer cells. This binds a tested **emulated** geometry; it does not approve a physical camera's writable interval.

Hooks monitor the job getter/setter, LCD input start, RAW-source setup and SSS-source store. Read-only run 27 observes unchanged sampled words over a 191,744 us guest-clock hold and no monitored consumer overlaps. After the stage returns, callbacks observe the same source at `0xff16ceb4` and RAW descriptor `0xc1770` at `0xff437d58`; the getters use the current capture job. No claim is made that these six hooks cover every possible physical-camera consumer.

An attempted second shot then exposed another emulator assumption: Canon coalesces the JPEG suite from eight chunks into one. [qemu-cr2-repeat-experiment.patch](qemu-cr2-repeat-experiment.patch) is the latest cumulative emulator patch against the same pin. The bounded B00 parser now accepts 1..16 chunks, checks pool bounds, capacity, address range and pairwise nonoverlap, and writes only the JPEG's byte count. ASan/UBSan exercises every accepted count plus malformed cases. The thumbnail/development outputs remain synthetic gray.

Run 28 completes two explicitly armed mirrored shots in a single boot:

| Mode | Canon file | All RAW pixels checked | Changed pixels | Unchanged margin pixels | Guest transform time |
|---|---|---|---|---|---|
| Right half, divisor 2 | IMG_0065.CR2 | 20,646,144 | 9,357,615 | 684,288 | 114,176 us |
| All edges, divisors 3/3 | IMG_0066.CR2 | 20,646,144 | 16,636,640 | 684,288 | 142,592 us |

Both files decode exactly to a separate Python oracle that maps Bayer cells from the independent generated-sensor pattern. The RAW strip also equals the actual JP57 output. Monitored overlaps, Canon assertions and invalid-memory reads were zero. The second shot has a different capture-job pointer and the same reused sensor buffer. Guest times are affected by emulation and are **not physical-camera performance measurements**.

Build/validate with:

```text
python tools/build_70d_research.py --runtime wsl
python scripts/test_70d_raw_probe.py --runtime wsl --qemu-run .cache/70d-capture27/read-only --qemu-run .cache/70d-capture28/right-half --qemu-run .cache/70d-capture28/all-thirds --refused-run .cache/70d-capture26
```

The builder writes only `build/70d-native-probe/` and its separate staging module, audits platform-header exclusion and all 23 imports against the coherent 70D core, and byte-compares the stripped debug object with the actual `.mo`. It never replaces `mirror.mo` or a candidate ZIP. The guarded ROM header is generated only after verifying the full ROM1 hash. No ROM is packaged.

In GDB, load the matching core ELF and add `build/70d-native-probe/m70raw.debug.o` at address 0 for its types. After connecting to QEMU, source `tools/qemu_70d_raw_probe.gdb.py`. `m70raw-arm 1 2 2 2` requests a read-only hold; `m70raw-arm 2 2 2 2` selects right-half mirroring; `m70raw-arm 2 15 3 3` selects all thirds. Wait for report phase 1 before triggering Canon Release through the separate DryOS `qprobe` driver. `m70raw-status` reads the module-owned report. The controller refuses operation without QEMU's remote extension. The probe is not installed in normal camera candidates.

The report is `build/tests/70d-raw-probe/results.json`; the frozen receipt is `build/70d-native-probe/70D.112-probe-observation.json`. Snapshot-backed receipts preserve their original path/hash mapping and original receipt bytes so later working-source/test edits do not erase historical evidence. Normal `mirror.mo` controls, LiveView delivery, automatic shutter latching, all remaining settings, cancellation/shutdown and a camera-specific backend are still required. Physical-camera validation and the other eligible model ports remain separate work.

## Dev6 main-module expired-latch fixture

The new `tests/qemu_native_flow/` helper exercises the real research `mirror.mo`, rather than the isolated `m70raw` probe. It invokes the normal menu API, feeds one owned synthetic LCD frame through the actual renderer, releases its temporary arena, enables the module's native gate, then explicitly calls its full-press latch and Canon's `Release` from a DryOS task. The source and receipt label this as a software full-press and synthetic preview; it does not establish normal hardware-key handling or real Canon LiveView. The helper is unshipped. It defers dependency checks to commands because ML initializes `mflow` before `mirror` in name order.

The research module is built into a fresh directory so the earlier dev3 observation and normal dev6 candidate remain intact:

```sh
python tools/build_module.py --module mirror --upstream --research-70d --research-output build/research/NEW-70D-EXPERIMENT --runtime wsl --wsl-user root
```

`--research-output` requires the research flag, stays under `build/research/` and refuses an existing target. The measured dev6 module is `build/research/mirror-70D.112-dev6-flow/mirror.mo` (SHA-256 `797bef2c6a0f7f03a152f51cb52583ce6252c1b3907792d1d4c809a13ee4e1de`). The VM uses the unchanged cumulative research emulator, SHA-256 `0a038ab5963a229d89fdd5874b11f0c06084bb5d6a5ce11fa43f57a90da97cf0`.

Run `.cache/70d-mainflow-dev6-v2` observes one delivered fixture frame, all five trace hooks and the capture-stage hook installed, and a latched request. Canon leaves LV and reaches the real main-module stage callback. The gate then reports `MG_NO_SHUTTER` with `latched=1`: the five-second latch deadline has expired. Recorded entry/full-press timestamps differ by about 9,996 ms; Canon logs two engine resource/wait errors during the interval. This connects the main-module path to Canon's capture stage, but it does not complete a mirrored capture. The production deadline is unchanged.

The refusal happens before a scheduling hold or pixel mutation: `held_us`, `patch_started`, `patch_done`, `patch_verified`, `patch_mismatches` and `patch_changed` are all zero. Canon still completes `IMG_0065.CR2` (20,797,364 bytes). Independent LibRaw decoding checks all **20,646,144 RAW pixels** against the separate generated-sensor oracle and finds them unchanged. The normal OFF command succeeds, preview allocations return to zero, no Canon assert/unmapped access is observed, and the owned VM exits normally through QMP.

Validate the stopped run with:

```sh
python scripts/test_main_capture_refusal.py --run .cache/70d-mainflow-dev6-v2 --module-build build/research/mirror-70D.112-dev6-flow --output NEW-REFUSAL-REPORT.json
```

The verifier refuses to overwrite its output. Unit tests reject an unlatched/unexpired request or any pixel-processing evidence as this negative fixture. The frozen receipt is `build/research/mirror-70D.112-dev6-flow/70D.112-main-flow-refusal.json`, with 110 evidence files plus the original receipt preserved under `evidence/`. It includes source, main/helper binaries, observations, the generated CR2 and decoder inputs; no ROM dump or virtual card is copied into that receipt.

The 70D backend remains disabled in the normal shared candidate. This dev6 run did not establish real LV activation/delivery, capture-stage timing after LV exit, the normal physical-key path or a mirrored CR2 through the main module. The later dev9 experiment below completes one main-module capture with synthetic inputs; this negative fixture remains historical evidence.

## Dev9 main-module saved RAW capture

The dev9 research `mirror.mo` now completes one **Right / Half** capture through its actual native gate and Canon's file writer. Independent LibRaw decoding matches **all 20,646,144 RAW pixels** against a separate same-CFA-phase interpolation reference: zero mismatches, 9,356,603 changed pixels, and all 684,288 optical-black margin pixels unchanged. The saved `IMG_0065.CR2` is 19,813,095 bytes, SHA-256 `ed7db4a0941ac472eb4dcda3e42fe52fd4dd8382f3098a2882a88d17d4366055`. Its compressed RAW strip also matches the emulator encoder's output byte for byte.

This uses the existing unshipped `mflow` helper: one owned synthetic preview, an explicit software full-press latch and Canon `Release`. Sensor input is generated. **Real Canon LiveView delivery, the physical shutter-key path, hardware timing and other settings are not established by this capture.** The normal universal dev9 module remains unchanged and keeps 70D native capture disabled.

The earlier five-second timeouts were in the emulator's missing FB/FC preprocessing completion path. ROM callbacks `0xff42e134` and `0xff42e0d0` register interrupts D0 and D1; observed block-start writes are `C0F1B300=1` and `C0F1B340=8`. The [completion-only model](qemu/fencing_research.inc.c) consumes an existing connection-14 host buffer only for the exact guarded DMA configuration in [fencing-research.json](fencing-research.json), then schedules the corresponding interrupt. It performs no FB/FC image processing and leaves the existing dummy output unchanged. It requires `QEMU_EOS_FENCING_RESEARCH=1`, 70D firmware 112, DIGIC 5 and the earlier research capture model.

Model v1 refused completion because its assumed output flags/FC geometry differed from the observed state. V2 completed too early: the DMA pointer had advanced before its interrupt fired, so Canon unregistered the read handler before that interrupt arrived and reported illegal interrupt C1. V3 follows the engine's existing simulated 200 MiB/s scheduling rule, completing one tick after the input DMA interrupt: FB after 5 ticks, FC after 314 ticks. These are emulator scheduling values, not physical-camera timings. The standalone ASan/UBSan fixture checks 16 rejected configurations, read-only/no-prior-FB refusal, both delays and duplicate-interrupt prevention.

Run `.cache/70d-mainflow-dev9-fencing-v3/` uses the isolated main module SHA-256 `c9ccc16dbbe658796009d378086488ee9363ac60f57332c6bb58d649dae3b482` and completion-only emulator SHA-256 `33d70b6d70850a27ed6eb99cff235538461d04446f5e8b10a4d3669c12d30e6b`. The cumulative [qemu-fencing-experiment.patch](qemu-fencing-experiment.patch) applies alone to fork commit `147d913fa455d217190509cd8f090546149d377b`; it includes the earlier CR2 adapter. The stock pinned emulator is unchanged.

The gate reaches its RAW stage 244.288 ms after latching without changing the production deadlines. It reports `MG_DONE`, zero error/overlap/source changes, 896 verified sampled words and zero sampled mismatches. Its emulated hold is 332,032 us, including 220,672 us processing. The private workspace is released after capture, OFF returns preview allocations to zero, and the owned VM exits with code 0 after QMP `quit`. These timings are development observations only.

The verifier binds the matching main/helper card modules, coherent core/autoexec/symbol cohort, emulator source and binary, unchanged normal module/source, structured observations and full pixel reference. Recheck the preserved local run into a fresh report:

```powershell
python scripts/test_main_registered_capture.py --run .cache/70d-mainflow-dev9-fencing-v3 --module-build build/research/mirror-70D.112-dev9-flow --qemu-build build/qemu-eos-70d-fencing-v3 --input-receipt .cache/qemu-inputs/70D.112.json --output build/research/NEW-MAIN-CAPTURE-REPORT.json
```

The snapshot-backed receipt is `build/research/mirror-70D.112-dev9-flow/70D.112-main-registered-receipt.json`. It preserves byte-exact evidence and the original path/hash mapping; no ROM or virtual card is copied. Reproduction launcher, command driver, GDB observer and guard-fixture log are included as additional local evidence. `--main-capture-report` attaches this receipt to the official-camera matrix as **research main-module CR2** evidence, independently of normal native support and owner hardware validation.

## Repeated main-module capture regression

The ticketed `mflow` helper and [native regression runner](../../tools/run_native_capture.py) extend that one-shot result. One boot first latches and cancels a capture before sensor processing, verifies release of its private lease, and recovers through the normal menu OFF/ON calls. It then takes three Canon photos without restarting or switching the effect OFF between shots: **Right/Half**, **All edges/Third**, and **Top/Half**. Separate capture jobs reuse the same sensor buffer. The gate's fresh latch time, completed command ticket and saved filename distinguish each photo from the previous one.

Independent LibRaw checks match **61,938,432 RAW pixels** across the three files, with zero mismatches. Every photo preserves all 684,288 margin pixels. This exercises horizontal, combined horizontal/vertical and vertical transforms through the actual main gate, not just a small-buffer kernel call. Final OFF returns the preview allocation and private workspace to zero; the owned VM stops through QMP with exit code 0. Native 70D capture stays disabled in the normal module.

The first sequence stopped before the third frame because Canon had not restored LV after file completion. Waiting and sending the emulator's LV key also failed to restart that state. The final fixture explicitly requests Canon's `PROP_LV_ACTION=0` through the existing property API while no capture job is active. **This software LV_START is an additional fixture limitation**, alongside synthetic preview/sensor data, software full-press/Release and completion-only preprocessing. It does not verify physical-key handling, real Canon LV delivery, hardware timing or all 44 full-flow settings. The failed runs remain under `build/research/native-flow-dev9-sequence-v1/` and `v2/`.

The first completed sequence, `native-flow-dev9-sequence-v3`, exposed a post-shutdown extraction assumption: the seed card uses `100EOS5D`, not `100CANON`. Its photos were recovered from the stopped card and all pixels verified. The final runner discovers the actual DCIM folder and refuses missing/ambiguous filenames. It copies its own launch sources and validates main/helper/core/card hashes. No original card image or ROM is altered, and no ROM/card is included in frozen evidence.

Build the unshipped helper against the exact research module, then use fresh output paths:

```powershell
python -m tools.build_native_flow_control --mirror-build build/research/mirror-70D.112-dev9-flow --output build/research/NEW-NATIVE-CONTROL
python -m tools.run_native_capture --mirror-build build/research/mirror-70D.112-dev9-flow --helper-build build/research/NEW-NATIVE-CONTROL --qemu-build build/qemu-eos-70d-fencing-v3 --input-receipt .cache/qemu-inputs/70D.112.json --output build/research/NEW-NATIVE-SEQUENCE
python scripts/test_native_capture_sequence.py --run build/research/NEW-NATIVE-SEQUENCE --output build/research/NEW-NATIVE-SEQUENCE/70D.112-sequence-receipt.json
python tools/freeze_research_receipt.py build/research/NEW-NATIVE-SEQUENCE/70D.112-sequence-receipt.json
```

The final sequence receipt is `build/research/native-flow-dev9-sequence-v4/70D.112-sequence-receipt.json`. Use `--native-sequence-report` when generating the official-camera matrix to attach this separate research category. It never changes the normal profile's native-capture or hardware-test status. The helper remains unshipped and the normal dev9 candidate bytes are preserved.
