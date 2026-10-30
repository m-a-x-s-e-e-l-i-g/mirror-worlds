/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "mirror_camera.h"
#include "mirror_capture_gate.h"
#include "mirror_raw_trace.h"
static const char *model,*firmware;
int is_camera(const char*m,const char*f){return !strcmp(model,m)&&!strcmp(firmware,f);}
int main(void)
{
    const char*profiles[][2]={{"EOSM","2.0.2"},{"5D2","2.1.2"},{"5D3","1.1.3"},{"5D3","1.2.3"},
        {"6D","1.1.6"},{"7D","2.0.3"},{"50D","1.0.9"},{"60D","1.1.1"},{"70D","1.1.2"},
        {"100D","1.0.1"},{"550D","1.0.9"},{"600D","1.0.2"},{"650D","1.0.4"},{"700D","1.1.5"},{"1100D","1.0.5"}};
    for(unsigned i=0;i<sizeof(profiles)/sizeof(*profiles);i++){
        model=profiles[i][0];firmware=profiles[i][1];
        assert(mirror_select_camera());assert(!strcmp(mirror_camera_name(),model));
        assert(!mirror_camera_native());
        mirror_dma_info dma;memset(&dma,0xa5,sizeof(dma));mirror_dma_info original=dma;
        assert(!mirror_camera_dma(0,&dma));assert(!memcmp(&original,&dma,sizeof(dma)));
        assert(!mirror_gate_request()&&!mirror_gate_request_source()&&!mirror_gate_request_patch()&&!mirror_gate_request_full());
        assert(!mirror_raw_trace_request());
        mirror_gate_automatic(1);mirror_gate_full_press();mirror_gate_reader(0xffffffff);
        mirror_gate_service();mirror_raw_trace_runtime();mirror_raw_trace_service();
        mirror_gate_cancel();mirror_raw_trace_cancel();mirror_gate_shutdown();mirror_raw_trace_shutdown();
        mirror_gate_report gate;mirror_raw_trace_report trace;
        memset(&gate,0xa5,sizeof(gate));memset(&trace,0xa5,sizeof(trace));
        mirror_gate_status(&gate);mirror_raw_trace_status(&trace);
        assert(gate.phase==MG_IDLE&&!gate.installed&&!gate.latched&&!gate.patch_done);
        assert(trace.phase==MT_IDLE&&!trace.installed&&!trace.events);
        firmware="0.0.0";assert(!mirror_select_camera());assert(!mirror_camera_native());
    }
    puts("Preview-only variant: 15 profiles refuse native requests without hardware imports");
    return 0;
}
