# Mirror Worlds 0.3.0

By **Max Seelig (MAXmade)**. Original Canon EOS M / firmware **2.0.2** /
Magic Lantern dev **2025-06-20**, source `ed3e7c0`.

## Install once

With the camera **OFF**, replace only **ML/MODULES/mirror.mo** using the module
inside this ZIP. Keep your current Magic Lantern installation. Leave older
glock and other MAXmade effects disabled, then restart.

## Normal use

Use **A+ / Auto ISO / Canon RAW / single-shot drive**, native **1x LCD** and
**Global Draw ON**. Open **Shoot → Mirror Worlds** and its controls submenu.
Turn **Live effect ON**, choose the edges and border sizes, then close the menu.

Compose and use the **physical shutter**. Release it between photos. The module
mirrors the sensor samples before Canon saves its **CR2**, and Canon handles
immediate review and Play/gallery. Capture automatically rearms. You can change
settings and take the next picture without arming a test or restarting.

There are **no diagnostic actions, menu photo saves, TIFF/DNG exports or routine
logs**. ON/OFF and every setting save automatically; restarting restores the
last choice. If left ON, it resumes when LiveView is ready. Settings changes
while half-pressed apply after release; the saved RAW uses the last delivered
composition.

## Settings

| Mirror on | Width | Height | Result |
|---|---|---|---|
| Left | Half–Sixth | Not used | Replace the left border with its neighbouring reflection |
| Right | Half–Sixth | Not used | Replace the right border |
| Top | Not used | Half–Sixth | Replace the top border |
| Bottom | Not used | Half–Sixth | Replace the bottom border |
| Left + Right | Third–Sixth | Not used | Original center strip, mirrored side borders |
| Top + Bottom | Not used | Third–Sixth | Original center strip, mirrored top/bottom |
| All edges | Third–Sixth | Third–Sixth | Original center rectangle, reflected sides and corners |

Fractions are **the size of EACH mirrored border**. Nothing is resized.
Opposing edges skip Half to leave an original center. Changing to an opposing
layout automatically changes an existing Half size to Third. Width and Height
remain independent and are remembered even when one is currently unused.

Examples:

- **Right / Half:** the original centered left-to-right mirror.
- **Left / Half:** the opposite direction.
- **Bottom / Third:** bottom third reflects the adjacent part above it.
- **Left + Right / Quarter:** central half unchanged, outer quarters reflected.
- **All edges / Quarter / Quarter:** central rectangle with mirrored borders;
  corner regions reflect in both directions.

## Try every option in the same build

There are **44 usable combinations**: five each for Left, Right, Top and Bottom;
four each for Left + Right and Top + Bottom; and sixteen Width/Height
combinations for All edges. Select a combination, close the menu and shoot.
No separate package, logging step or test action is needed between choices.
A normal power-off/restart also lets you check that your last settings return.

## Preferences and capture limits

The module saves two small checked preference files, `mirror0.prf` and
`mirror1.prf`, in Magic Lantern's current settings directory. These are automatic
preferences, not diagnostic logs; you do not need to manage them. The previous
valid slot survives an interrupted new save. Global ML autosave settings and
other modules' preferences are not changed.

Native Canon RAW copies original samples without averaging. Fold axes sit on
sensor rows/columns to preserve both fine detail and Bayer color alignment;
they differ by half a sensor pixel from a between-pixel reflection. Processing
covers the full visible RAW image, including pixels outside Canon's smaller
JPEG crop. Optical-black rows and columns remain unchanged.
More mirrored area may take longer to process. Single shots are supported;
continuous drive, remote triggers, video and long exposures are outside this
release's workflow.

Wait for **ON - Ready**, half-press to focus, then press fully to take a photo.
Mirrored LiveView continues during focusing. If capture reports **Capture
stopped**, retain its number/help text, turn Live effect OFF/ON to retry, or
restart. A rejected capture may remain unmirrored; the module stops instead of
silently continuing. The complete fold finishes once sensor writing has begun.
Power OFF before replacing/removing the module; runtime hooks remain until then.

## Verification

The EOS M owner accepted the dev14 candidate's capture and image quality for
this release. Version 0.3.0 retains its processing code with a release version
label. Independent tests compare all 44 layouts against exact original samples
on full-sized synthetic RAW frames. Separate color-registration and ARM tests
check the fold geometry, packed pixels, bounds, cancellation and module
lifecycle. These automated results do not mean all camera modes were tested.

The original EOS M is the only camera-tested native RAW target. The same
module contains experimental LiveView-only profiles for additional cameras;
their saved photos remain original, and they have not been hardware validated.
Use the existing Magic Lantern core for your exact model/firmware. Older API-7
cores cannot load this API-8 release. See the repository's camera compatibility
guide before trying it on another camera.
