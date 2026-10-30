/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef MIRROR_CAMERA_H
#define MIRROR_CAMERA_H
#include <stdint.h>
#include "fx_namespace.h"
#define mirror_select_camera FX(camera_select)
#define mirror_camera_name FX(camera_name)
#define mirror_camera_native FX(camera_native)
#define mirror_camera_dma FX(camera_dma)
#define MIRROR_NATIVE_POINTS 8u
enum {MIRROR_DMA_DIGIC5=1};
typedef struct {uint32_t pc,words[4],kind;} mirror_hook;
/* Module-owned data, never a Canon/DryOS or camera-dependent core struct. */
typedef struct {
    uint32_t stage_pc,stage_words[4],stage_context,stage_caller,stage_job_offset;
    uint32_t stage_cpsr_mask,stage_cpsr_value,source_alignment_mask;
    mirror_hook points[MIRROR_NATIVE_POINTS];
    uint32_t point_count,trace_start_pc,dma_kind;
    uint32_t raw_desc,sss_desc,jpeg_desc,raw_context,sss_context;
    uint32_t alias_bit,origin_offset,width,height,pitch,sensor_bytes;
    uint32_t readout_offset,readout_bytes,readout_xn,readout_flags;
    uint32_t region[4];
} mirror_native_backend;
typedef struct {
    uint32_t off1a,off1b,off2a,off2b,off3,xa,xb,ya,yb,xn,yn;
} mirror_dma_info;
/* Select once at module init, before tasks, handlers, or memory access.
 * Preview candidates are explicitly listed; native support is independent. */
int mirror_select_camera(void);
const char *mirror_camera_name(void);
const mirror_native_backend *mirror_camera_native(void);
int mirror_camera_dma(unsigned channel,mirror_dma_info *out);
/* Core scalar interfaces have no per-camera struct-return ABI. */
uint32_t edmac_get_flags(uint32_t channel);
uint32_t edmac_get_state(uint32_t channel);
uint32_t edmac_get_address(uint32_t channel);
uint32_t edmac_get_pointer(uint32_t channel);
#endif
