Native flow fixture
===================

:Author: Max Seelig (MAXmade)
:License: GPL-2.0-or-later
:Summary: Unshipped 70D QEMU main-module capture fixture
:Version: 0.0.3

Feeds an owned synthetic preview through the loaded research mirror.mo.
Then explicitly invokes its full-press latch and Canon Release from DryOS.
This is not a physical shutter test or real LiveView evidence. It installs
no native hooks itself and is never included as a camera module candidate.

Commands: 1 menu ON, 2 deliver an owned synthetic frame, 3 arm the actual
main gate, 4 full-press plus Canon Release, 5 menu OFF, 6 Canon RAW quality,
7 latch then cancel without taking a photo, 8 request Canon LV_START through
the existing property API while no capture job is active. Edges/width/height configure
command 2. Each command carries a ticket; completed_ticket prevents a
previous identical command from being mistaken for the current response.
Only queue when command=0 and completed_ticket matches the preceding ticket.
