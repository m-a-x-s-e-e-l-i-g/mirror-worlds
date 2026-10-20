/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef FX_MIRROR_RAW_H
#define FX_MIRROR_RAW_H
#include "fx_effect.h"
#include "glitchlock.h"
#define fx_mirror_raw_prepare FX(mirror_raw_prepare)
#define fx_mirror_raw_point FX(mirror_raw_point)
#define fx_mirror_raw_row FX(mirror_raw_row)
#define fx_mirror_raw_sample FX(mirror_raw_sample)
typedef struct {int32_t x,y,a,b,c,d;} fx_mirror_raw_sector;
typedef struct {
    uint32_t magic;
    gl_frame source;
    fx_params params;
    uint32_t left,top,right,bottom,cells_w,cells_h;
    int32_t center_x,center_y;
    fx_mirror_raw_sector sector[12];
    volatile int *stop;
} fx_mirror_raw;
/* Region is top,left,bottom,right in full sensor coordinates. Map its even
 * 2x2-cell interior; margins, odd boundary samples and padding remain original.
 * The source must have a proved stable lease through every subsequent read.
 * This context owns no sensor memory and never writes source samples. */
FX_API int fx_mirror_raw_prepare(fx_mirror_raw*m,const gl_frame*source,
    const uint32_t region[4],const fx_params*p,volatile int*stop);
FX_API int fx_mirror_raw_point(const fx_mirror_raw*m,unsigned x,unsigned y,unsigned out[2]);
/* Decode/map one full sensor row to 14-bit values in uint16_t. No full-frame
 * destination or heap allocation; output must be disjoint from source/context.
 * Returns FX_OK/FX_INVALID/FX_CANCEL; partial cancelled rows cannot be saved. */
FX_API int fx_mirror_raw_row(const fx_mirror_raw*m,unsigned y,uint16_t*out,size_t samples);
FX_API int fx_mirror_raw_sample(const fx_mirror_raw*m,unsigned x,unsigned y,uint16_t*out);
#endif
