/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "gl_review.h"
#include <string.h>
static void dismiss(gl_review *r) { r->state = GL_R_OFF; r->revision++; }
static void centered(gl_review *r) { r->zoom = 1; r->center_x = r->center_y = 32768; }
void gl_review_init(gl_review *r)
{
    memset(r, 0, sizeof(*r)); r->configured_ms = 3000; centered(r);
}
int gl_review_duration(gl_review *r, uint32_t ms)
{
    if (ms != 2000 && ms != 3000 && ms != 5000) return GL_INVALID;
    r->configured_ms = ms; return GL_OK;
}
void gl_review_publish(gl_review *r, uint32_t image_id, uint32_t now)
{
    r->have_image = 1; r->image_id = image_id; r->error = 0;
    r->duration_ms = r->configured_ms; r->queued_ms = now; r->started_ms = 0;
    r->state = GL_R_WAITING; r->revision++; centered(r);
}
void gl_review_fail(gl_review *r, uint32_t error) { r->error = error; dismiss(r); }
void gl_review_half(gl_review *r, int down)
{
    if (down && !r->half_down && r->state) dismiss(r);
    r->half_down = down != 0;
}
static uint32_t move(uint32_t value, int delta)
{
    int next = (int)value + delta;
    return next < 0 ? 0 : next > 65536 ? 65536 : (uint32_t)next;
}
int gl_review_key(gl_review *r, uint32_t key, uint32_t now)
{
    if (key == GL_R_PLAY) {
        if (r->state) dismiss(r);
        else if (r->have_image) {
            centered(r); r->state = GL_R_MANUAL; r->revision++; r->queued_ms = now;
        } else return GL_BUSY;
        return GL_OK;
    }
    if (!r->state) return GL_BUSY;
    if (key == GL_R_DISMISS) { dismiss(r); return GL_OK; }
    if (key > GL_R_DOWN) return GL_INVALID;
    r->state = GL_R_MANUAL; r->revision++;
    if (key == GL_R_ZOOM_IN && r->zoom < 4) r->zoom *= 2;
    if (key == GL_R_ZOOM_OUT && r->zoom > 1) r->zoom /= 2;
    if (key == GL_R_LEFT) r->center_x = move(r->center_x, -8192);
    if (key == GL_R_RIGHT) r->center_x = move(r->center_x, 8192);
    if (key == GL_R_UP) r->center_y = move(r->center_y, -8192);
    if (key == GL_R_DOWN) r->center_y = move(r->center_y, 8192);
    return GL_OK;
}
void gl_review_tick(gl_review *r, uint32_t now)
{
    if (r->state == GL_R_TIMED && (uint32_t)(now - r->started_ms) >= r->duration_ms) dismiss(r);
    else if (r->state == GL_R_WAITING && (uint32_t)(now - r->queued_ms) >= 2000) gl_review_fail(r, GL_R_DISPLAY);
}
int gl_review_delivered(gl_review *r, uint32_t revision, uint32_t now)
{
    if (!r->state || r->revision != revision) return GL_BUSY;
    if (r->state == GL_R_WAITING) { r->state = GL_R_TIMED; r->started_ms = now; }
    return GL_OK;
}
int gl_review_scale(const void *source, size_t source_size, void *dest, size_t dest_size,
                    uint32_t width, uint32_t height, uint32_t pitch,
                    uint32_t zoom, uint32_t center_x, uint32_t center_y, volatile int *stop)
{
    if (!source || !dest || !width || (width & 1) || !height || width > 720 || height > 480 ||
        pitch < width * 2 || pitch > 4096 || (zoom != 1 && zoom != 2 && zoom != 4) ||
        center_x > 65536 || center_y > 65536) return GL_INVALID;
    size_t bytes = (size_t)pitch * height;
    uintptr_t s = (uintptr_t)source, d = (uintptr_t)dest;
    if (source_size < bytes || dest_size < bytes || s > UINTPTR_MAX - bytes || d > UINTPTR_MAX - bytes ||
        (s < d + bytes && d < s + bytes)) return GL_INVALID;
    uint32_t pairs = width / 2, span_x = pairs / zoom, span_y = height / zoom;
    if (!span_x || !span_y) return GL_INVALID;
    uint32_t x0 = (pairs - span_x) * center_x / 65536;
    uint32_t y0 = (height - span_y) * center_y / 65536;
    const unsigned char *src = source; unsigned char *dst = dest;
    for (uint32_t y = 0; y < height; ++y) {
        if (stop && *stop) return GL_BUSY;
        uint32_t sy = y0 + y * span_y / height;
        for (uint32_t x = 0; x < pairs; ++x) {
            uint32_t sx = x0 + x * span_x / pairs;
            memcpy(dst + (size_t)y * pitch + x * 4, src + (size_t)sy * pitch + sx * 4, 4);
        }
    }
    return GL_OK;
}
