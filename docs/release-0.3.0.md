# Mirror Worlds 0.3.0 — sharper RAW reflections

Mirror Worlds 0.3.0 preserves fine texture and grain in mirrored RAW areas, covers the full visible RAW image, and fixes shutter capture on the original EOS M.

## Changes

- **Sharper mirrored detail:** original 14-bit sensor samples are copied without averaging. All color planes share the same fold axis, avoiding the earlier cell-reversal alignment error. Each RAW fold sits on a sensor row or column, half a pixel from the previous between-pixel axis.
- **Mirrored RAW edges:** processing includes the extra image pixels RAW converters expose outside Canon's smaller JPEG crop, removing the thin unmirrored outer strips. Optical-black margins remain untouched.
- **Reliable EOS M shutter preparation:** half-press prepares capture, and mirrored LiveView continues while focusing. A focus hold keeps the latch current; releasing without a photo expires quietly.
- **Less RAW processing work:** packed row copies and grouped pixel access reduce instruction cost. Camera saving/review time still depends on the scene, settings and card; emulator timings are not camera benchmarks.
- **Readable capture errors:** the menu shows a numeric code and a useful reason when capture stops.
- **Runtime camera profiles:** the source selects camera capabilities automatically. Additional listed profiles are experimental LiveView previews; native mirrored CR2 capture remains EOS M only.

## Compatibility

Camera tested and accepted by MAXmade on the **original Canon EOS M, firmware 2.0.2**, using **Magic Lantern dev 2025-06-20 / EOSM.202**. Use **A+ / Auto ISO / Canon RAW / single-shot drive**, native 1× LCD LiveView and Global Draw ON. Magic Lantern must already be installed. Other cameras, EOS M models, camera modes and ML builds have not received that hardware acceptance.

The release promotes the accepted **0.3.0-dev14** processing code with a stable version label. The automated checks cover exact sample preservation, Bayer registration, all 44 layouts on full-sized synthetic RAW frames, capture refusal/cancellation and ARM module execution. They do not establish additional physical-camera support.

## Install or upgrade

1. Power the camera **OFF** and retain your previous module if you want a rollback.
2. Extract **MIRROR-0.3.0-EOSM202.zip** and copy `ML/MODULES/mirror.mo` into the same folder on the card.
3. Enable `mirror.mo` in Magic Lantern's Modules tab and restart. Existing Mirror Worlds preferences are retained.
4. Open **Shoot → Mirror Worlds**, enable the effect, wait for **ON - Ready**, then half-press to focus and press fully to take a photo.

Use single RAW photos and release the shutter between shots. Bursts, video, remote triggers and long exposures remain outside the supported workflow. Turn the camera off before replacing/removing the module. The download contains no Canon updater, replacement ML core or ROM.

## Downloads

- **MIRROR-0.3.0-EOSM202.zip** — recommended; module, exact source, license and build metadata.
- **mirror.mo** — the same camera module on its own.
- **SHA256SUMS** — checksums for both downloads.

The previous 0.2.0 release remains available unchanged.
