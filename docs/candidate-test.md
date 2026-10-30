# Mirror Worlds 0.3.0-dev14 camera test candidate

This is a development build. The published 0.2.0 download remains the camera-tested EOS M release. Keep your working module and settings so you can restore them.

Dev14 addresses the soft mirrored noise/detail confirmed in the owner's dev13 CR2. It copies original 14-bit RAW samples without averaging. Fold axes now sit on sensor rows/columns: the last border sample for Top/Left, the first for Bottom/Right. This moves each axis by half a pixel from the earlier between-sample fold, preserves the Bayer color pattern, and avoids the old cell-reversal color misregistration. The full RAW bounds and working half-shutter path are retained. Test a fresh CR2 with fine texture and compare its mirrored section with the unchanged source. Existing photos have already lost the averaged detail; this build applies to new captures.

Dev13 fixes the thin unmirrored border found in the owner's EOS M CR2. Earlier candidates mirrored only Canon's 5184x3456 default JPEG crop, while LibRaw exposes 5208x3476 image pixels. The EOS M processing rectangle now includes that full decoder-visible area, leaving optical-black rows/columns outside it untouched. The nominal fold positions move by a few pixels because border sizes now use the larger rectangle. See `source/docs/eosm-raw-bounds.md` for the measured geometry and regression evidence. Fresh camera confirmation of the expanded edges is still required.

The EOS M owner confirmed that dev11 fixes capture error **7 (missing shutter latch)**, then reported a shutter-to-review delay of more than three seconds. Dev12 reduced work in the then-current averaging kernel. Dev14 removes that averaging: vertical folds copy packed rows, and horizontal folds decode only the required source bands. Canon14 groups retain aligned word accesses where possible. The independent reference now checks exact original samples and geometric/color registration; camera timing still needs comparison.

The dev11 shutter fix is retained. The pinned EOS M core has a half-shutter event but no full-shutter GUI mapping. The module prepares its capture latch from the available physical half-shutter key/property. Its small RAW workspace uses a separate tail after the preview canvas, so focusing can continue to show the effect. Holding half-press keeps the latch fresh during valid LiveView; releasing without taking a photo expires quietly. The guarded Canon capture callback still requires an actual capture job and completed RAW readout before writing pixels.

The dev10 numeric/readable error display is retained. If capture stops, report the number and help text. On EOS M, first wait for **ON - Ready**, then half-press to focus and press fully to take a single photo. Compare shutter-to-review time against dev11 using the same scene, exposure, card, file format, edge layout and size. Inspect all the way to each selected edge in the RAW editor's full image, as well as the camera preview. Top/Bottom with Third reproduces the supplied photo's layout; also check All edges. Also check a quick full click, a focus hold of more than five seconds, and half-press/release without a photo. LiveView should remain mirrored during focusing, and half-press alone must not take a photo.

Native mirrored RAW capture is implemented only for the original **EOS M, Canon firmware 2.0.2**. This build retains cancellation and processing checks, and uses the new exact-sample color-aligned reflection. Real-camera speed and saved CR2 quality still need fresh EOS M testing.

One shared `mirror.mo` covers the API-8 profiles below. Earlier dev9 tests loaded that binary in the available 70D emulator and passed synthetic preview/RAW checks, with no real Canon LiveView frames. Those observations are historical, not a dev14 firmware run. The other firmware runs lack ROM inputs. Source checks and synthetic tests do not establish physical-camera compatibility.

Detailed background is included under `source/docs/portability.md`, `source/docs/cfa-registration.md` and `source/docs/raw-processing-cost.md` in the ZIP. Historical dev9 observations do not attest these new module bytes. No ML core, Canon updater, emulator helper binary or ROM is included.

The following profiles have **LiveView preview only**. Their saved photos remain original:

| Camera | Canon firmware |
|---|---|
| 100D | 1.0.1 |
| 1100D | 1.0.5 |
| 50D | 1.0.9 |
| 550D | 1.0.9 |
| 5D Mark II | 2.1.2 |
| 5D Mark III | 1.1.3 or 1.2.3 |
| 600D | 1.0.2 |
| 60D | 1.1.1 |
| 650D | 1.0.4 |
| 6D | 1.1.6 |
| 700D | 1.1.5 |
| 70D | 1.1.2 |
| 7D | 2.0.3 |

None of these additional profiles has been camera validated. This standard API-8 module is incompatible with the cached older 7D API-7 build. For an existing 7D API-7 installation, use the separate preview experiment and `source/docs/api7-preview-test.md`; saved photos remain original. Do not replace a working ML core to try this module. The included `CORE-AUDIT.json` identifies source-core checks for these exact bytes; it is not a camera test.

## Install and check

1. Use a spare card with a working Magic Lantern installation for your exact camera and firmware. Save the previous `mirror.mo` and both `mirror0.prf` / `mirror1.prf` files from the active ML settings directory, if present. Temporarily remove those backed-up preference files from the test card for a fresh OFF start. This ZIP contains no replacement ML core or Canon updater.
2. Turn the camera off. Copy `ML/MODULES/mirror.mo` from this ZIP to the same folder on the card. Enable `mirror.mo` in ML's Modules tab and restart. Disable other MAXmade effects for this test.
3. Before enabling the effect, check normal autofocus, shutter, review and playback. Use photo mode, RAW and single-shot drive. Set Global Draw ON and native 1× LCD LiveView, with no external monitor.
4. Open **Shoot → Mirror Worlds**. Check that the effect starts OFF on a fresh settings file. Turn it ON. On other camera profiles the help must describe LiveView-only operation and original RAW photos. The status may show **ON - Preparing** until frames arrive, then **ON - Preview only**. Try left, right, top, bottom, both sides and all edges; change sizes and compare the preview. Test the 1100D's shorter LCD frame for correct alignment.
5. Take single photos using the normal shutter and check autofocus, Canon image review and playback. Preview-only profiles must save normal, unmirrored photos. On EOS M, start with the tested A+ / Auto ISO workflow and confirm that the mirror is actually in the CR2 using a RAW editor. Photograph the same fine-detail scene with the effect OFF and ON, especially All edges / Third. Keep both original CR2 files and record all capture and RAW-converter settings. Compare color detail, fold alignment and the outer image boundary.
6. Turn the effect OFF and confirm normal LiveView and photos. Restart and check saved preferences. Test menu entry/exit and a temporary zoom change for stale or damaged previews. Stop if the camera hangs or behaves unexpectedly; retain the exact steps and logs for investigation.

Do not hot-unload this development module after enabling native capture; switch the camera off before replacing or removing it. To restore the old installation, power off, restore the old module/settings, and restart.

## Report a result

Record the exact model, Canon firmware, ML build date/revision, candidate module SHA256, menu capability, which steps passed, and any failure steps. Attach original and effect CR2 files for EOS M capture comparisons, and camera screenshots for preview problems. State explicitly whether a result came from a camera or an emulator. Do not distribute ROM dumps with the report.

This candidate is a step toward mirrored RAW support on the eligible cameras. Preview success does not complete that work.
