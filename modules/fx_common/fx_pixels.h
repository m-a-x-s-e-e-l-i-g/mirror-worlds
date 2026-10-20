/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef FX_PIXELS_H
#define FX_PIXELS_H
#include <stdint.h>
#include <stddef.h>
#include "fx_namespace.h"
#if defined(_WIN32) && defined(GL_EXPORT_FX)
#define FX_API __declspec(dllexport)
#else
#define FX_API
#endif
typedef struct { uint32_t direction, speed, width; } fx_slit_params;
typedef struct {
    fx_slit_params params;
    uint32_t initialized, width, height, cursor, credit, last_ms, frames, gaps, paused_ms;
} fx_slit;
/* Directions: left->right, right->left, top->bottom, bottom->top. Speed/width
 * in LCD pixels. Propose into disjoint destination/state/timestamps; caller
 * commits only after display delivery. Timestamp units are wrapping camera ms. */
FX_API int fx_slit_step(const fx_slit *old, fx_slit *next, const void *source,
    const void *history, void *destination, size_t capacity, uint32_t width,
    uint32_t height, uint32_t pitch, const uint32_t *old_times,
    uint32_t *new_times, const fx_slit_params *params, uint32_t now);
typedef int (*fx_write_fn)(void *,const void *,size_t);
enum { FX_OK, FX_INVALID, FX_IO, FX_CANCEL };
/* Render signed UYVY to an uncompressed RGB TIFF. Workspace needs width*3
 * disjoint bytes. The supplied snapshot remains immutable throughout. */
FX_API int fx_tiff_write(const void *source, size_t capacity, uint32_t width,
    uint32_t height, uint32_t pitch, void *workspace, size_t work_size,
    fx_write_fn write, void *context, volatile int *stop);
FX_API int fx_tiff_write_ex(const void *source,size_t capacity,uint32_t width,
    uint32_t height,uint32_t pitch,void *workspace,size_t work_size,
    fx_write_fn write,void *context,volatile int *stop,const char *description);
#endif
