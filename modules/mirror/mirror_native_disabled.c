/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef MIRROR_PREVIEW_ONLY
#error This implementation is only for an explicit preview-only build
#endif
#include <string.h>
#include "mirror_capture_gate.h"
#include "mirror_raw_trace.h"
/* No hook code, sensor reads, task introspection or patch-manager imports.
 * The normal source build still links the complete EOS M capture backend. */
void mirror_gate_automatic(unsigned enabled){(void)enabled;}
int mirror_gate_request(void){return 0;}
int mirror_gate_request_source(void){return 0;}
int mirror_gate_request_patch(void){return 0;}
int mirror_gate_request_full(void){return 0;}
void mirror_gate_service(void){}
void mirror_gate_full_press(void){}
void mirror_gate_half_press(unsigned down){(void)down;}
void mirror_gate_reader(unsigned pc){(void)pc;}
void mirror_gate_cancel(void){}
void mirror_gate_shutdown(void){}
void mirror_gate_status(mirror_gate_report*out){if(out)memset(out,0,sizeof(*out));}
void mirror_raw_trace_runtime(void){}
int mirror_raw_trace_request(void){return 0;}
void mirror_raw_trace_service(void){}
void mirror_raw_trace_cancel(void){}
void mirror_raw_trace_shutdown(void){}
void mirror_raw_trace_status(mirror_raw_trace_report*out){if(out)memset(out,0,sizeof(*out));}
