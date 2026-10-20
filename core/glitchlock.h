/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GLITCHLOCK_H
#define GLITCHLOCK_H
#include <stddef.h>
#include <stdint.h>

#ifdef _WIN32
#define GL_API __declspec(dllexport)
#else
#define GL_API
#endif

#define GL_OPS 12
enum gl_format { GL_U16 = 0, GL_CANON14 = 1 };
enum gl_effect { GL_ROW_SHIFT = 0, GL_BLOCK_SWAP = 1, GL_BIT_CRUSH = 2 };
enum gl_state { GL_LIVE = 0, GL_FROZEN, GL_SAVING, GL_REVIEW, GL_ERROR };
enum gl_result { GL_OK = 0, GL_INVALID = -1, GL_BUSY = -2 };

/* Coordinates are relative to the active image, in units of 1/65536.
 * Spatial operations move complete 2x2 Bayer cells, preserving CFA phase. */
typedef struct { uint32_t x, y, w, h, dx, dy; } gl_op;
typedef struct {
    uint32_t seed, effect, intensity;
    gl_op ops[GL_OPS];
} gl_plan;
typedef struct {
    void *data;
    size_t size;
    uint32_t width, height, pitch, format, black, white;
} gl_frame;
typedef struct {
    uint32_t state, sequence, half_down, review_ms, review_started;
    gl_plan live, locked, captured;
} gl_session;

GL_API int gl_make_plan(gl_plan *plan, uint32_t seed, uint32_t effect, uint32_t intensity);
/* Destination must be disjoint, have identical geometry and contain a copy of
 * any sensor metadata outside this frame. Source and padding are preserved.
 * An unpaired final row in an odd-height frame is copied unchanged. */
GL_API int gl_apply(const gl_frame *src, gl_frame *dst, const gl_plan *plan);
/* Active sensor region: leave optical black margins and row padding intact. */
GL_API int gl_apply_region(const gl_frame *src, gl_frame *dst, const gl_plan *plan,
                          uint32_t x, uint32_t y, uint32_t width, uint32_t height);
GL_API int gl_unpack14(const gl_frame *src, uint16_t *out, size_t samples);
GL_API int gl_pack14(const uint16_t *src, size_t samples, gl_frame *dst);
/* Decode one row into caller-owned samples without changing frame or padding. */
GL_API int gl_read_row16(const gl_frame *src, uint32_t y, uint16_t *out, size_t samples);
GL_API void gl_init(gl_session *session, uint32_t seed, uint32_t effect, uint32_t intensity);
GL_API int gl_configure(gl_session *session, uint32_t effect, uint32_t intensity);
GL_API void gl_advance(gl_session *session);
GL_API void gl_half_press(gl_session *session, int down);
GL_API int gl_capture(gl_session *session);
/* Call only after persistence AND review image preparation succeeded. */
GL_API int gl_saved(gl_session *session, int success, uint32_t now);
GL_API void gl_tick(gl_session *session, uint32_t now);
GL_API void gl_dismiss(gl_session *session);
#endif
