/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef FX_DIFFRACT_H
#define FX_DIFFRACT_H
#include "fx_effect.h"
#define fx_diffract_size FX(diffract_size)
#define fx_diffract_validate FX(diffract_validate)
#define fx_diffract_ready FX(diffract_ready)
#define fx_diffract_prepare FX(diffract_prepare)
#define fx_diffract_render FX(diffract_render)
#define FX_DIFFRACT_TAPS 2307u
#define FX_DIFFRACT_SOURCES 64u
typedef struct {int16_t x,y;uint16_t weight;uint8_t channel,pad;} fx_diffract_tap;
typedef struct {int32_t x,y;uint32_t strength,pixels,cells;} fx_diffract_peak;
typedef struct {uint16_t weight,x,y;uint8_t peak,count;} fx_diffract_cell;
typedef struct {
    uint32_t magic,width,height,pitch,tap_count;
    fx_params params;
    fx_diffract_tap taps[FX_DIFFRACT_TAPS];
    fx_diffract_peak peaks[FX_DIFFRACT_SOURCES];
    uint16_t row[182][3]; /* Vertical Q8 light interpolation with zero borders. */
    unsigned char data[];
} fx_diffract_work;
#define FX_DIFFRACT_WORKSPACE (sizeof(fx_diffract_work)+12u*180u*120u)
/* Params: blade count 3..8 (two stylized rays per blade), green radius
 * 8..160 native px/multiple of 4, spectral spread, threshold Y, amount,
 * halo-ring amount. Spread/amount/halo are 0..100; threshold is 0..255.
 * Reduced quarter-resolution RGB light layer, native base scene. */
FX_API size_t fx_diffract_size(unsigned width,unsigned height);
FX_API int fx_diffract_validate(const fx_params*p);
FX_API int fx_diffract_ready(const void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch);
FX_API int fx_diffract_prepare(void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch,volatile int*stop);
/* stats: bright pixels, connected regions, retained sources, kernel taps,
 * dropped regions, light width/height. Workspace is transient per frame. */
FX_API int fx_diffract_render(const void*source,void*dest,size_t capacity,void*workspace,size_t work_size,
    const fx_params*p,unsigned width,unsigned height,unsigned pitch,uint32_t stats[7]);
#endif
