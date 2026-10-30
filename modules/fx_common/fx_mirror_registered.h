/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef FX_MIRROR_REGISTERED_H
#define FX_MIRROR_REGISTERED_H
#include "fx_mirror_raw.h"
#define fx_mirror_registered_workspace FX(mirror_registered_workspace)
#define fx_mirror_registered_apply FX(mirror_registered_apply)
/* Rectangular edge maps only. Prepared Canon14 input, immutable private map,
 * exclusively owned sensor buffer and disjoint private workspace are caller
 * preconditions. This primitive establishes no Canon timing/ownership contract.
 * Workspace is two packed rows, including pitch padding. Same-CFA-phase
 * exact reflection uses axes on integer sensor samples: low axis at the last
 * border sample, high axis at the first. Source parity equals destination
 * parity on both axes; original 14-bit samples are copied without averaging,
 * clipping or plane-dependent offsets. Optical black and padding are unchanged.
 * The retained two-row workspace holds one decoded row for horizontal copies.
 * Odd-address workspace retains the scalar exact-copy fallback. No allocation,
 * file IO, Canon calls or cache op.
 * Cancellation is checked before writes; after the first write it completes.
 */
size_t fx_mirror_registered_workspace(const fx_mirror_raw*map);
int fx_mirror_registered_apply(const fx_mirror_raw*map,void*owned,size_t capacity,
                               void*workspace,size_t workspace_bytes);
#endif
