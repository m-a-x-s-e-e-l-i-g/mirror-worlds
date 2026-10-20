/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef FX_MIRROR_H
#define FX_MIRROR_H
#include "fx_effect.h"
#define fx_mirror_size FX(mirror_size)
#define fx_mirror_validate FX(mirror_validate)
#define fx_mirror_ready FX(mirror_ready)
#define fx_mirror_prepare FX(mirror_prepare)
#define fx_mirror_render FX(mirror_render)
#define FX_MIRROR_OFFSET 0x001fffffu
#define FX_MIRROR_ODD 0x00200000u
typedef struct {uint32_t a,b;} fx_mirror_pair;
typedef struct {uint16_t end,sector;} fx_mirror_run;
typedef struct {int32_t a,b,c,d;} fx_mirror_matrix;
typedef struct {uint16_t end,swap;uint32_t start;int32_t step;} fx_mirror_xrun;
typedef struct {
    uint32_t magic,width,height,pitch,mode;
    fx_params params;
    uint32_t x[720],y[480];
    int32_t center_x,center_y;
    fx_mirror_matrix matrix[12];
    uint16_t fold_x[3072],fold_y[3072],run_count[480];
    uint32_t fast_count;
    fx_mirror_xrun fast[16];
    fx_mirror_run runs[][16];
} fx_mirror_map;
#define FX_MIRROR_MAX_WORKSPACE (sizeof(fx_mirror_map)+480u*16u*sizeof(fx_mirror_run))
FX_API size_t fx_mirror_size(unsigned width,unsigned height);
FX_API int fx_mirror_validate(const fx_params*p);
FX_API int fx_mirror_ready(const void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch);
FX_API int fx_mirror_prepare(void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch,volatile int*stop);
FX_API int fx_mirror_render(const void*source,void*dest,size_t capacity,const void*w,size_t n,
    const fx_params*p,unsigned width,unsigned height,unsigned pitch);
#endif
