/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef FX_MIRROR_SENSOR_H
#define FX_MIRROR_SENSOR_H
#include "fx_mirror_raw.h"
#define fx_mirror_sensor_pack FX(mirror_sensor_pack)
#define fx_mirror_sensor_axial FX(mirror_sensor_axial)
#define fx_mirror_sensor_inplace_size FX(mirror_sensor_inplace_size)
#define fx_mirror_sensor_inplace FX(mirror_sensor_inplace)
/* Process into a separately owned, packed Canon14 buffer, suitable as input
 * to Canon compression once the capture layer proves its handoff. No file IO.
 * Source/context/work/destination must not alias (including EOSM cache aliases).
 * Work needs source.width uint16_t samples; destination padding is untouched.
 * Failure/cancel may leave PARTIAL DESTINATION DATA: never publish that buffer.
 * No allocation. Source remains unchanged on success and all failures. */
FX_API int fx_mirror_sensor_pack(const fx_mirror_raw*m,void*destination,size_t capacity,
    unsigned pitch,uint16_t*work,size_t work_samples);
/* Zero-snapshot primitive: centered 2/4 reflections at axis 0 or 90,
 * or rectangular borders encoded by FX_MIRROR_EDGES (fx_mirror_edges.h).
 * Every mapped source cell is a fixed point and is never overwritten. Thus
 * cell order is immaterial. Edge corners read the original center directly.
 * Copy fixed packed spans and reverse four cells
 * per complete Canon14 group; scalar edges preserve neighboring fields.
 * Only bounded local temporaries, no external scratch or sensor snapshot.
 * General geometry can use the bitmap-ordered helper or separate output above.
 * EXCLUSIVE OWNERSHIP is the caller's precondition, not established here.
 * owned must equal m->source.data, with a coherent CPU alias. Canon14 only.
 * Stop is honored before writes; once started it completes the transform,
 * because a partially changed Canon buffer must never resume compression.
 * This is not connected to a camera callback or the read-only QR probe. */
FX_API int fx_mirror_sensor_axial(const fx_mirror_raw*m,void*owned,size_t capacity);
/* All prepared Mirror geometries, with five three-state cells per scratch
 * byte: ceil(active 2x2 Bayer cells / 5). No full sensor copy, allocation, IO
 * or Canon calls. Source cells are a functional graph: peel all consumers
 * with no remaining dependents,
 * then rotate the residual cycles using one four-sample temporary.
 * A complete dry pass validates closed mappings and cancellation BEFORE the
 * first sensor write. After writing starts, finish without consulting stop.
 * owned must equal source.data (coherent Canon14 CPU alias) and be exclusively
 * owned until completion. Context and scratch must remain private/immutable
 * to other tasks. Scratch contents are unspecified after every call. Failure
 * or pre-write cancellation leaves sensor bytes unchanged. This primitive
 * does NOT establish that Canon may wait, a camera lease, or cache coherence.
 * It is not connected to the camera probe/hooks or any photo writer. */
FX_API size_t fx_mirror_sensor_inplace_size(const fx_mirror_raw*m);
FX_API int fx_mirror_sensor_inplace(const fx_mirror_raw*m,void*owned,size_t capacity,
    void*workspace,size_t workspace_size);
#endif
