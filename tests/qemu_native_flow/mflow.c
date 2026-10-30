/* SPDX-License-Identifier: GPL-2.0-or-later; unshipped QEMU fixture only. */
#include <module.h>
#include <dryos.h>
#include <config.h>
#include <menu.h>
#include <lens.h>
#include <vram.h>
#include <string.h>
#include "fx_camera.h"
#include "mirror_camera.h"
#include "mirror_capture_gate.h"
extern void *__priv_shoot_malloc(size_t);
extern void __priv_shoot_free(void*);
extern int pic_quality;
CONFIG_INT("mirror.flow.command",command,0);
CONFIG_INT("mirror.flow.completed",completed,0);
CONFIG_INT("mirror.flow.result",result,0);
CONFIG_INT("mirror.flow.frames",frames,0);
CONFIG_INT("mirror.flow.ticket",ticket,0);
CONFIG_INT("mirror.flow.completed_ticket",completed_ticket,0);
CONFIG_INT("mirror.flow.edges",edges,2);
CONFIG_INT("mirror.flow.width",width,2);
CONFIG_INT("mirror.flow.height",height,2);
static volatile int stopping,finished;
static int delivered_fixture(void)
{
    if(!mirror_camera_native()||!fx_filter(0)||lens_info.job_state)return -10;
    struct vram_info *v=get_yuv422_vram();
    if(!v||v->width!=720||v->height!=480||v->pitch!=1440)return -11;
    unsigned bytes=(unsigned)v->pitch*v->height;
    mirror_gate_automatic(0);
    /* Temporary owned fixture arena; released before native capture is armed.
     * This is not the production preview allocator and requests no photo. */
    unsigned char *arena=__priv_shoot_malloc(2*bytes);
    if(!arena)return -12;
    for(unsigned i=0;i<bytes;i++)arena[i]=(unsigned char)((i*37)^(i>>7));
    memset(arena+bytes,0xa5,bytes);
    struct display_filter_buffers buffers={arena,arena+bytes};
    fx_params params={{180,(unsigned)edges,(unsigned)width,(unsigned)height}};int outcome=-13;
    if(fx_controls(&params))for(unsigned retry=0;retry<10&&!stopping;retry++){
        msleep(20);fx_filter(&buffers);fx_state state;
        if(fx_delivered_state(&state)&&!memcmp(&state.params,&params,sizeof(params))){outcome=1;frames++;break;}
    }
    __priv_shoot_free(arena);return outcome;
}
static void worker(void*unused)
{
    (void)unused;
    while(!stopping){
        unsigned action=(unsigned)command;command=0;
        if(action){
            int request_ticket=ticket;
            int value=-1;
            if(action==1)value=menu_set_value_from_script("Shoot","Mirror Worlds",1);
            if(action==2)value=delivered_fixture();
            if(action==3&&mirror_camera_native()){mirror_gate_automatic(1);value=1;}
            if(action==4&&mirror_camera_native()){
                mirror_gate_report r;mirror_gate_status(&r);
                if(r.phase==MG_ARMED){mirror_gate_full_press();mirror_gate_status(&r);
                    value=r.latched?call("Release"):-15;
                }else value=-14;
            }
            if(action==5)value=menu_set_value_from_script("Shoot","Mirror Worlds",0);
            if(action==6){int quality=PICQ_RAW;prop_request_change(PROP_PIC_QUALITY,&quality,4);msleep(500);value=pic_quality;}
            if(action==7&&mirror_camera_native()){
                mirror_gate_full_press();mirror_gate_report r;mirror_gate_status(&r);
                if(r.latched){mirror_gate_cancel();value=1;}else value=-15;
            }
            if(action==8&&!lens_info.job_state){int start=0;prop_request_change(PROP_LV_ACTION,&start,4);value=1;}
            result=value;completed=(int)action;completed_ticket=request_ticket;
            DryosDebugMsg(0,15,"MFLOW command=%x result=%d ticket=%d",action,value,request_ticket);
        }
        msleep(100);
    }
    finished=1;
}
static unsigned init(void)
{
    /* ML initializes modules in name order; mirror may initialize after us.
     * Commands check native capability after the loader has finished. */
    if(!is_camera("70D","1.1.2"))return 1;
    stopping=finished=command=completed=result=frames=ticket=completed_ticket=0;
    edges=width=height=2;
    uintptr_t task=(uintptr_t)task_create("mirror_flow",0x1e,0x4000,worker,0);
    return !task||task==0xffffffffu;
}
static unsigned deinit(void){stopping=1;for(unsigned i=0;i<100&&!finished;i++)msleep(20);return !finished;}
MODULE_INFO_START() MODULE_LONGNAME("QEMU native flow") MODULE_INIT(init) MODULE_DEINIT(deinit) MODULE_INFO_END()
MODULE_CBRS_START() MODULE_CBRS_END()
MODULE_PROPHANDLERS_START() MODULE_PROPHANDLERS_END()
MODULE_CONFIGS_START() MODULE_CONFIG(command) MODULE_CONFIG(completed) MODULE_CONFIG(result) MODULE_CONFIG(frames)
MODULE_CONFIG(ticket) MODULE_CONFIG(completed_ticket) MODULE_CONFIG(edges) MODULE_CONFIG(width) MODULE_CONFIG(height) MODULE_CONFIGS_END()
