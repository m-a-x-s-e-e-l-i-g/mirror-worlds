/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef FX_NAMESPACE_H
#define FX_NAMESPACE_H
#ifndef FX_PREFIX
#define FX_PREFIX slitscan
#endif
#define FX_JOIN_(a,b) a##_##b
#define FX_JOIN(a,b) FX_JOIN_(a,b)
#define FX(n) FX_JOIN(FX_PREFIX,n)
#define fx_slit_step FX(slit_step)
#define fx_tiff_write FX(tiff_write)
#define fx_tiff_write_ex FX(tiff_write_ex)
#define gl_snprintf FX(snprintf)
#define gl_vsnprintf FX(vsnprintf)
#define gl_review_init FX(review_init)
#define gl_review_duration FX(review_duration)
#define gl_review_publish FX(review_publish)
#define gl_review_fail FX(review_fail)
#define gl_review_half FX(review_half)
#define gl_review_key FX(review_key)
#define gl_review_tick FX(review_tick)
#define gl_review_delivered FX(review_delivered)
#define gl_review_scale FX(review_scale)
#endif
