Mirror Worlds
=============

:Author: Max Seelig (MAXmade)
:License: GPL-2.0-or-later
:Summary: Live edge reflections and native mirrored Canon RAW
:Version: 0.3.0

Development candidate; new camera testing required.
Native RAW backend: original EOS M, Canon 2.0.2.
Other eligible cameras: LiveView preview only; photos stay original.
See docs/portability.md in the source repository for the candidate list.
Unknown models/firmware refuse initialization before starting a task.

Shooting
--------

A+ / Auto ISO / Canon RAW / single-shot drive.
Native 1x LCD and Global Draw ON.
Shoot / Mirror Worlds: open the controls submenu.
Enable Live effect, choose your edges and sizes, close the menu.
Compose and use the physical shutter. Release between photos.
On EOS M 2.0.2, Canon saves mirrored CR2 and handles quick review and Play.
On preview-only cameras, the menu says Preview only and RAW stays original.
Capture rearms automatically; no test actions or menu export.

Mirror on
---------

Left / Right / Top / Bottom / Left + Right /
Top + Bottom / All edges.
This chooses which areas get replaced by reflections.
The source area remains unchanged. No image resizing.
Corners reflect both directions when All edges is selected.
Right / Half reproduces the original centered mirror.

Border size
-----------

Width and Height: Half / Third / Quarter / Fifth / Sixth.
These fractions measure EACH mirrored border.
Width is unused for Top/Bottom; Height unused for Left/Right.
Opposing edges skip Half so the original center survives.
Left + Right / Quarter keeps the central half unchanged.
All edges / Quarter / Quarter surrounds a central rectangle.
Sensor boundaries align to complete Bayer cells.

Remembering settings
--------------------

ON/OFF, placement, Width and Height survive restart.
If last left ON, preview and capture resume when LiveView is ready.
Normal capture uses the last delivered/half-locked composition.
Settings save automatically without a manual logging step.
Two checked preference slots retain the previous valid save.
No other Magic Lantern preferences are changed.

Installation
------------

With camera OFF, replace only ML/MODULES/mirror.mo.
Restart with older glock and other effects disabled.
Only one MAXmade effect may run at a time.
Keep your existing autoexec.bin and firmware.
Use the standard Modules loader and a full power OFF to restart.
Do not dynamically unload or replace the running module.

Capture protection
------------------

Runtime-selected firmware/caller/source/DMA checks remain active.
A capture fault stops the effect; switch OFF/ON to retry.
A rejected capture can remain unmirrored.
Once writing begins, the complete fold finishes.
Sensor margins and optical black stay unchanged.
Single shots only; bursts, video and long exposures unsupported.
No TIFF/DNG, companion original or routine diagnostic logs.
