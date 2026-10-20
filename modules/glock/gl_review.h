/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GL_REVIEW_H
#define GL_REVIEW_H
#include "glitchlock.h"
enum { GL_R_OFF, GL_R_WAITING, GL_R_TIMED, GL_R_MANUAL };
enum { GL_R_PLAY, GL_R_DISMISS, GL_R_ZOOM_IN, GL_R_ZOOM_OUT,
       GL_R_LEFT, GL_R_RIGHT, GL_R_UP, GL_R_DOWN };
enum { GL_R_MEMORY = 100, GL_R_RENDER, GL_R_DISPLAY };
typedef struct {
    uint32_t state, have_image, revision, image_id, configured_ms, duration_ms;
    uint32_t queued_ms, started_ms, half_down, zoom, center_x, center_y, error;
} gl_review;
GL_API void gl_review_init(gl_review *r);
GL_API int gl_review_duration(gl_review *r, uint32_t ms);
GL_API void gl_review_publish(gl_review *r, uint32_t image_id, uint32_t now);
GL_API void gl_review_fail(gl_review *r, uint32_t error);
GL_API void gl_review_half(gl_review *r, int down);
GL_API int gl_review_key(gl_review *r, uint32_t key, uint32_t now);
GL_API void gl_review_tick(gl_review *r, uint32_t now);
GL_API int gl_review_delivered(gl_review *r, uint32_t revision, uint32_t now);
/* Worker-only nearest UYVY-pair zoom. Disjoint full-size buffers, signed chroma
 * preserved byte-for-byte; coordinates are normalized 0..65536. */
GL_API int gl_review_scale(const void *source, size_t source_size, void *dest, size_t dest_size,
                          uint32_t width, uint32_t height, uint32_t pitch,
                          uint32_t zoom, uint32_t center_x, uint32_t center_y,
                          volatile int *stop);
#endif
