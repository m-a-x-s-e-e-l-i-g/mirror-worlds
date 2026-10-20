/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef FX_EFFECT_H
#define FX_EFFECT_H
#include "fx_pixels.h"
typedef struct {uint32_t value[8];} fx_params;
typedef struct {
    fx_params params;
    uint32_t initialized,width,height,last_ms,frames,gaps;
    uint32_t data[32]; /* Effect-owned scalar state, privately copied per frame. */
} fx_state;
typedef struct {
    const char *module,*title,*version,*prefix,*log_prefix,*kind,*description;
    unsigned param_count,temporal; /* 0 spatial; 1 slice times; 2 feedback; 3 tile times. */
    const char *param_names[8];
    fx_params defaults;
    size_t workspace_size;
    int (*validate)(const fx_params*);
    int (*ready)(const void*,size_t,const fx_params*,unsigned,unsigned,unsigned);
    int (*prepare)(void*,size_t,const fx_params*,unsigned,unsigned,unsigned,volatile int*);
    int (*render)(const fx_state*,fx_state*,const void*,const void*,void*,size_t,
        unsigned,unsigned,unsigned,const uint32_t*,uint32_t*,const fx_params*,unsigned,void*,size_t);
    unsigned (*time_count)(const fx_params*,unsigned,unsigned);
    /* Optional comma-terminated JSON fragment from the immutable saved state.
     * Return required length, or negative on failure; no image access or IO. */
    int (*metadata)(const fx_state*,char*,size_t);
} fx_effect;
extern const fx_effect FX(effect);
#endif
