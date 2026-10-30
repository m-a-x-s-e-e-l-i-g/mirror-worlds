# Experimental API-7 preview candidate

This separate build is intended for a **7D owner already using a working API-7 ML installation on Canon 2.0.3**. It has not been loaded in a real 7D or a 7D firmware emulator. Do not replace a working ML core to try it. The usual API-8 candidate remains the main build; EOS M owners should use that build for native RAW testing.

The variant uses the same renderer, controls and preferences, compiled against pinned historical API-7 headers. Native hook code is excluded, and every native capture request is refused. **Photos stay original.** Its menu must say preview only, including when the module recognizes an EOS M; no native RAW backend is available in this variant. Only the cached 7D distribution has received the export check for this binary.

Before distribution, keep the accompanying `PACKAGE.json`, source, SDK provenance and validation receipt with this module. Resolved imports, SDK structure checks and host tests do not establish the installed core's layout or prove module initialization.

The current dev9 API-7 file also passes a [ROM-free ARM binary fixture](emulation.md#automated-universal-baseline): it is linked unchanged into a simulated SDK and exercises menu/property/preview/preferences/cleanup code for all 15 profile inputs on two CPU models. This is not the ML loader or a Canon 7D boot. The matrix keeps that synthetic evidence separate from owner results; it does not extend the archive/export check to other API-7 installations.

## Owner check

1. Start with a spare card containing your already working 7D / Canon 2.0.3 ML installation. Back up the existing `mirror.mo` and `mirror0.prf` / `mirror1.prf` preferences, if present. Remove the backed-up preferences from the test card for a fresh OFF start.
2. With the camera off, copy this package's `ML/MODULES/mirror.mo` onto the card. Enable it in ML's Modules tab and restart. If loading fails, record the full error and stop this test.
3. Check autofocus, shutter, review and playback before enabling the effect. Set photo mode, single-shot drive, Global Draw ON and native 1x LCD LiveView. Disable other MAXmade effects.
4. Open Shoot → Mirror Worlds. It must start OFF. Turn it ON and confirm the preview-only indication. Try each mirror placement and size. Check image alignment and transitions through the ML menu, Canon review and a temporary zoom change.
5. Take a normal photo. Its saved JPEG/RAW must remain original. Turn the effect OFF, confirm normal LiveView, then restart and check that preferences are remembered. If a hang occurs, retain the last action and any ML crash log.
6. To restore the old installation, turn the camera off, restore the previous module/preferences and restart.

Report model, Canon firmware, ML build date/revision, candidate SHA-256, load result, ON/OFF result, saved-photo result and exact failure steps. Label real-camera and emulator reports separately. No ROM dump is needed with the report.

## Rebuild

From Windows with WSL Ubuntu and the existing ARM toolchain:

```sh
python -m tools.build_api7_preview
```

The tool verifies historical SDK files against `targets/api7-sdk-inputs.json`, fetching only missing public files. It executes no downloaded build script. Outputs go to a fresh folder under `build/research/api7-preview/`; the normal API-8 module and released downloads are preserved. The package includes this guide, the exact `.mo`, source, historical SDK license/provenance, validation receipt and per-file hashes. The source-level native-disable mode is also exercised by `python scripts/test_portability.py --runtime wsl --sanitize`.
