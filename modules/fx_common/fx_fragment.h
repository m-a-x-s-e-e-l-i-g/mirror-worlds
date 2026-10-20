/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef FX_FRAGMENT_H
#define FX_FRAGMENT_H
#include "fx_effect.h"
#define fx_fragment_size FX(fragment_size)
#define fx_fragment_validate FX(fragment_validate)
#define fx_fragment_ready FX(fragment_ready)
#define fx_fragment_prepare FX(fragment_prepare)
#define fx_fragment_tiles FX(fragment_tiles)
#define fx_fragment_age FX(fragment_age)
#define fx_fragment_step FX(fragment_step)
#define FX_FRAGMENT_WORKSPACE (9u*360u*240u*2u)
/* Tile size in native pixels (24..240, multiple of four); sample period
 * 0 or 50..500ms; randomness 0..100; stable recipe seed 1..65535.
 * Eight committed 360x240 UYVY images and one unreferenced candidate slot.
 * data[0..11] stats, data[12..19] newest-first slot IDs, [20..27] times,
 * [28] parameter changes, [30..31] history geometry. */
FX_API size_t fx_fragment_size(unsigned width,unsigned height);
FX_API int fx_fragment_validate(const fx_params*p);
FX_API int fx_fragment_ready(const void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch);
FX_API int fx_fragment_prepare(void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch,volatile int*stop);
FX_API unsigned fx_fragment_tiles(const fx_params*p,unsigned width,unsigned height);
FX_API unsigned fx_fragment_age(const fx_params*p,unsigned column,unsigned row,unsigned columns);
FX_API int fx_fragment_step(const fx_state*old,fx_state*next,const void*source,void*dest,size_t capacity,
    void*workspace,size_t work_size,uint32_t*new_times,const fx_params*p,
    unsigned width,unsigned height,unsigned pitch,unsigned now);
#endif
