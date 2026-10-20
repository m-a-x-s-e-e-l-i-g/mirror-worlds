Mirror Worlds
=============

:Author: Max Seelig (MAXmade)
:License: GPL-2.0-or-later
:Summary: Live edge reflections and native mirrored Canon RAW
:Version: 0.2.0

Original EOS M, Canon 2.0.2, ML dev 2025-06-20 (ed3e7c0).

Shooting
--------

A+ / Auto ISO / Canon RAW / single-shot drive.
Native 1x LCD and Global Draw ON.
Shoot / Mirror Worlds: open the controls submenu.
Enable Live effect, choose your edges and sizes, close the menu.
Compose and use the physical shutter. Release between photos.
Canon saves mirrored CR2 and handles quick review and Play.
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

Pinned firmware/caller/source/DMA checks remain active.
A capture fault stops the effect; switch OFF/ON to retry.
A rejected capture can remain unmirrored.
Once writing begins, the complete fold finishes.
Sensor margins and optical black stay unchanged.
Single shots only; bursts, video and long exposures unsupported.
No TIFF/DNG, companion original or routine diagnostic logs.
