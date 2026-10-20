/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef FX_CAMERA_H
#define FX_CAMERA_H
#include "fx_pixels.h"
#include "fx_effect.h"
#include "gl_review.h"
#define fx_start FX(start)
#define fx_service FX(service)
#define fx_filter FX(filter)
#define fx_half FX(half)
#define fx_key FX(key)
#define fx_capture FX(capture)
#define fx_configure FX(configure)
#define fx_controls FX(controls)
#define fx_stop FX(stop)
#define fx_reset FX(reset)
#define fx_status_get FX(status_get)
#define fx_diagnostics FX(diagnostics)
#define fx_review_time FX(review_time)
#define fx_camera_init FX(camera_init)
#define fx_delivered_state FX(delivered_state)
#define fx_canon_gui FX(canon_gui)
#define fx_native_capture_mode FX(native_capture_mode)
#define fx_private_cpu_heap_mode FX(private_cpu_heap_mode)
#define fx_capture_scratch_configure FX(capture_scratch_configure)
#define fx_capture_scratch_acquire FX(capture_scratch_acquire)
#define fx_capture_scratch_release FX(capture_scratch_release)
extern int FX(active);
typedef struct {
    unsigned running, frames, discarded, half, frozen, error, render_ms, interval_ms;
    unsigned allocated, peak, capture, capture_error, request_ms, snapshot_ms;
    unsigned review_state, review_zoom, saved, gaps;
    unsigned preparing,prepare_ms;
    unsigned free_initial,free_failed,required,reserve,allocation_stage;
    unsigned kernel_ms,display_ms,commit_ms,max_interval_ms,zoom_resets,core_ready,zoom_active,native_capture;
    unsigned cpu_memory,cpu_mask,cpu_initial,cpu_failed,cpu_required,dma_required,cpu_reserve;
    unsigned private_dma_after,private_cpu_after;
    char path[64], log[64];
} fx_status;
/* Boot-time initialization only; never reset a running instance/active lease. */
void fx_camera_init(void);
int fx_delivered_state(fx_state*out);
/* Opt in to Canon Play/quick-review priority. Other module policies unchanged. */
void fx_canon_gui(unsigned state);
/* Before start only: no rendered export/review allocation. Does not implement
 * Canon RAW mutation. The module must preserve Canon's shutter/Play controls. */
int fx_native_capture_mode(void);
/* Boot/idle only, compiled opt-in for Feedback/Fragment private CPU buffers.
 * Keep both pool reserves; never use photo/SRM fallback or reduce image/history.
 * A successful planner decision is not a camera capacity/contiguity guarantee. */
int fx_private_cpu_heap_mode(void);
typedef struct {void *data;size_t size;unsigned generation;} fx_capture_scratch;
/* Optional native, non-temporal capture support. Configure before start only.
 * Allocate max(preview canvas, bytes), reusing that canvas during capture.
 * The normal allocator and 1.5 MiB reserve still apply; zero disables borrowing.
 * No module opts in automatically. These calls neither access Canon sensor
 * memory nor establish its ownership, coherence or a processing deadline. */
int fx_capture_scratch_configure(size_t bytes);
/* Nonblocking, no allocation/IO: acquire only between renders/preparations,
 * after a delivered frame. Failure leaves out unchanged. A successful lease
 * invalidates committed preview pixels and excludes even stale filter calls.
 * Keep the returned token private; release exactly that lease after all users
 * finish. Stop/shutdown retains the arena and family claim until release.
 * This is preview-memory ownership only, not a Canon sensor-buffer lease. */
int fx_capture_scratch_acquire(fx_capture_scratch *out);
int fx_capture_scratch_release(const fx_capture_scratch *lease);
int fx_start(void);
void fx_service(void);
unsigned int fx_filter(void *context);
void fx_half(int down);
int fx_key(unsigned key);
int fx_capture(void);
int fx_configure(const fx_slit_params *params);
int fx_controls(const fx_params *params);
void fx_stop(void);
void fx_reset(void);
void fx_status_get(fx_status *out);
void fx_diagnostics(void);
void fx_review_time(unsigned ms);
#endif
