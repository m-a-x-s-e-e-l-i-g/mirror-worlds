/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef FX_FEEDBACK_H
#define FX_FEEDBACK_H
#include "fx_effect.h"
#define fx_feedback_size FX(feedback_size)
#define fx_feedback_validate FX(feedback_validate)
#define fx_feedback_coefficients FX(feedback_coefficients)
#define fx_feedback_ready FX(feedback_ready)
#define fx_feedback_prepare FX(feedback_prepare)
#define fx_feedback_step FX(feedback_step)
#define FX_FEEDBACK_WORKSPACE (720u*480u*3u)
/* Params: zoom rate +100 (-50..100 %/s exponential rate), rotation +60
 * (-60..60 deg/s), decay (0..100 percent lost/second), X/Y drift +120.
 * Two stable 360x240 YUV histories with 8 fractional bits per component.
 * data[0] is the committed slot; a rejected next state leaves it immutable. */
FX_API size_t fx_feedback_size(unsigned width,unsigned height);
FX_API int fx_feedback_validate(const fx_params*p);
FX_API int fx_feedback_ready(const void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch);
FX_API int fx_feedback_prepare(void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch,volatile int*stop);
/* Q16 complex inverse transform, translation in history pixels, retain Q16. */
FX_API int fx_feedback_coefficients(const fx_params*p,unsigned dt,int32_t out[5]);
FX_API int fx_feedback_step(const fx_state*old,fx_state*next,const void*source,void*dest,size_t capacity,
    void*workspace,size_t work_size,const fx_params*p,unsigned width,unsigned height,unsigned pitch,unsigned now);
#endif
