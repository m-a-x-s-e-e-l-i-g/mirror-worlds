/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef MIRROR_PHOTO_PROBE_H
#define MIRROR_PHOTO_PROBE_H
#include "fx_effect.h"
#define mirror_photo_gui FX(photo_gui)
#define mirror_photo_property FX(photo_property)
#define mirror_photo_service FX(photo_service)
#define mirror_photo_status FX(photo_status)
#define mirror_photo_start FX(photo_start)
#define mirror_photo_signal FX(photo_signal)
#define mirror_photo_cancel FX(photo_cancel)
enum {MP_IDLE,MP_ARMED,MP_WAIT_QR,MP_RECHECK,MP_DONE,MP_FAILED};
enum {MP_OK,MP_NO_PREVIEW,MP_TIMEOUT,MP_NO_QR,MP_LV_ACTIVE,MP_NOT_RAW,MP_RAW_SETUP,MP_GEOMETRY,MP_DMA,MP_CHANGED,MP_CANCELLED,MP_LOG};
typedef struct {unsigned ms,kind,value,length,extra;} mirror_photo_event;
typedef struct {
    unsigned stage,error,request_id,request_ms,preview_ms,qr_ms,read_ms,recheck_ms,qr_events,polls;
    unsigned request_epoch,observed_epoch,gui_states,lv_states,mode,job;
    unsigned width,height,pitch,bytes,bits,active[4],crop[4],black,white,cfa;
    unsigned dma_state;uintptr_t dma_address,dma_pointer,buffer;
    unsigned request_exposure[4],sample_exposure[4],exposure_seen;
    unsigned source_hash,mapped_hash,stable_samples;
    unsigned request_kind,events,event_dropped;
    mirror_photo_event event[32];
    fx_params params;
    uint16_t x[64],y[64],source_values[64],mapped_values[64];
    char log[64];
} mirror_photo_report;
/* Read-only physical-photo observation window. Controls are latched when
 * observation starts, not at an unproved physical full-press signal. It never
 * requests a capture, changes Canon settings or consumes shutter events. */
int mirror_photo_start(const fx_state*delivered);
void mirror_photo_cancel(void);
/* kind 1=GUI, 2=SW2, 3=release, 4=counter, 5=raw key, 6=portable key. */
void mirror_photo_signal(unsigned kind,unsigned value,unsigned length,unsigned extra);
void mirror_photo_gui(unsigned state);
void mirror_photo_property(unsigned which,unsigned value);
void mirror_photo_service(void);
void mirror_photo_status(mirror_photo_report*out);
#endif
