/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mirror_camera_sdk.h"
#include "mirror_trace_sdk.h"
#include "mirror_camera.h"
#include "mirror_capture_gate.h"
#include "mirror_raw_trace.h"
#include "fx_preview.h"
#include "fx_mirror_edges.h"
static const char *model="",*firmware="";
static unsigned hardware_reads,hooks,rom_reads,clock_ms,bad_rom,fake_flags;
static uint32_t fake_xa,fake_xb,fake_xn,fake_off1;
static unsigned fake_busy,pixel_reads,pixel_pointers,yield_action,delivery=1;
static uint8_t *sensor;
static unsigned char scratch[32768];
static unsigned scratch_held,scratch_generation,scratch_refuse;
static fx_params controls={{FX_MIRROR_EDGES,FX_EDGE_RIGHT,2,2}};
#define SOURCE 0x01000000u
#define JOB 0x00200000u
static void (*stage_callback)(uint32_t*,uint32_t*,uint32_t);
int lv=1,lv_paused,gui_state,ml_shutdown_requested;
struct test_lens lens_info;
int is_camera(const char *m,const char *f){return !strcmp(m,model)&&!strcmp(f,firmware);}
unsigned cli(void){return 0;}
void sei(unsigned s){(void)s;}
unsigned get_ms_clock(void){return clock_ms;}
unsigned get_us_clock(void){return clock_ms*1000;}
void msleep(unsigned ms)
{
    clock_ms+=ms;
    unsigned action=yield_action;yield_action=0;
    if(action==1)mirror_gate_reader(mirror_camera_native()->points[2].pc);
    if(action==2)mirror_gate_cancel();
    if(action==3)mirror_gate_shutdown();
    if(action==4)fake_flags^=1;
    if(action==6){mirror_gate_automatic(0);mirror_gate_automatic(1);}
}
int get_current_task_id(void){return 1;}
int get_halfshutter_pressed(void){return 0;}
int gui_menu_shown(void){return 0;}
uint32_t edmac_get_base(uint32_t channel){hardware_reads++;return 0xc0f04000+channel*256;}
uint32_t shamem_read(uint32_t address)
{
    hardware_reads++;
    switch(address&255){case 0x14:return fake_xa;case 0x10:return fake_xb;case 0x0c:return fake_xn;case 0x20:return fake_off1;default:return 0;}
}
uint32_t edmac_get_state(uint32_t c){(void)c;hardware_reads++;return fake_busy;}
uint32_t edmac_get_flags(uint32_t c){(void)c;hardware_reads++;return fake_flags;}
uint32_t edmac_get_address(uint32_t c){(void)c;hardware_reads++;return sensor?SOURCE+mirror_camera_native()->readout_offset:0;}
uint32_t edmac_get_pointer(uint32_t c){(void)c;hardware_reads++;return sensor?SOURCE+mirror_camera_native()->readout_offset+mirror_camera_native()->readout_bytes:0;}
uint32_t mirror_trace_test_read32(uint32_t address)
{
    hardware_reads++;assert(sensor&&address==mirror_camera_native()->stage_context+mirror_camera_native()->stage_job_offset);return JOB;
}
uint16_t mirror_trace_test_read16(uint32_t address)
{
    hardware_reads++;pixel_reads++;const mirror_native_backend*n=mirror_camera_native();assert(sensor&&n);
    unsigned offset=(address&~n->alias_bit)-SOURCE-n->origin_offset;assert(offset+1<n->sensor_bytes);
    return sensor[offset]|((unsigned)sensor[offset+1]<<8);
}
void *mirror_trace_test_sensor_pointer(uint32_t address)
{
    pixel_pointers++;const mirror_native_backend*n=mirror_camera_native();assert(sensor&&n&&address==((SOURCE+n->origin_offset)|n->alias_bit));return sensor;
}
uint32_t read_value(uint8_t *address,int instruction)
{
    assert(instruction);rom_reads++;
    const mirror_native_backend*n=mirror_camera_native();assert(n);
    uint32_t a=(uint32_t)(uintptr_t)address;
    if(bad_rom==1&&a==n->points[n->point_count-1].pc+12)return 0;
    if(bad_rom==2&&a==n->stage_pc)return 0;
    for(unsigned i=0;i<n->point_count;i++)for(unsigned j=0;j<4;j++)if(a==n->points[i].pc+j*4)return n->points[i].words[j];
    for(unsigned j=0;j<4;j++)if(a==n->stage_pc+j*4)return n->stage_words[j];
    assert(!"unknown ROM address");return 0;
}
int patch_hook_function(uintptr_t address,uint32_t instruction,void (*cb)(uint32_t*,uint32_t*,uint32_t),const char *description)
{
    (void)instruction;(void)description;assert(mirror_camera_native());hooks++;
    if(address==mirror_camera_native()->stage_pc)stage_callback=cb;
    return 0;
}
int fx_delivered_state(fx_state *out){memset(out,0,sizeof(*out));out->initialized=1;out->params=controls;return delivery;}
int fx_capture_scratch_acquire(fx_capture_scratch*out)
{
    if(scratch_refuse||scratch_held||!delivery||!lv)return 0;
    scratch_held=1;*out=(fx_capture_scratch){scratch,sizeof(scratch),++scratch_generation};return 1;
}
int fx_capture_scratch_release(const fx_capture_scratch*lease)
{
    assert(scratch_held&&lease->data==scratch&&lease->generation==scratch_generation);
    scratch_held=0;return 1;
}
int fx_capture_scratch_ready(const fx_capture_scratch*lease)
{return scratch_held&&lease->data==scratch&&lease->generation==scratch_generation;}
static void rejected_capture(unsigned scenario,unsigned expected)
{
    const mirror_native_backend*n=mirror_camera_native();
    lv=1;lens_info.job_state=0;delivery=1;
    mirror_gate_automatic(0);mirror_gate_automatic(1);mirror_gate_service();
    mirror_gate_report r;mirror_gate_status(&r);assert(r.phase==MG_ARMED);
    if(scenario==8)delivery=0;
    scratch_refuse=scenario==14;
    if(scenario!=7)mirror_gate_full_press();
    scratch_refuse=0;
    fake_xa=fake_xb=n->pitch;fake_xn=n->readout_xn;fake_flags=n->readout_flags;fake_off1=fake_busy=0;
    uint32_t saved[16]={0};uint32_t*regs=saved+1;
    saved[0]=0x13;regs[0]=SOURCE;regs[10]=n->stage_context;regs[13]=n->stage_caller;
    lv=0;lens_info.job_state=1;
    if(scenario==0)fake_flags=0;
    if(scenario==1)fake_flags|=1;
    if(scenario==2)fake_xn++;
    if(scenario==3)fake_busy=1;
    if(scenario==4)fake_off1=1;
    if(scenario==5)regs[10]++;
    if(scenario==6)saved[0]|=0x80;
    if(scenario==9)regs[0]++;
    if(scenario>=10&&scenario!=14)yield_action=scenario-9;
    unsigned before=pixel_reads,pointers=pixel_pointers;
    stage_callback(regs,regs+14,n->stage_pc);mirror_gate_status(&r);
    if(r.phase!=MG_FAILED||r.error!=expected||r.patch_started||r.patch_done)
        fprintf(stderr,"Capture refusal scenario %u: phase=%u error=%u expected=%u started=%u done=%u\n",scenario,r.phase,r.error,expected,r.patch_started,r.patch_done);
    assert(r.phase==MG_FAILED&&r.error==expected&&!r.patch_started&&!r.patch_done);
    assert(!scratch_held);
    assert(pixel_pointers==pointers); /* No sensor mutation was attempted. */
    if(scenario<10||scenario==14)assert(pixel_reads==before); /* Reject before even reading pixels. */
    if(scenario>=10&&scenario!=14)assert(r.before_count==896&&!r.after_count);
    if(scenario==10)assert(r.overlaps==1&&r.first_overlap_pc==n->points[2].pc);
    if(scenario==11||scenario==13)yield_action=0;
    delivery=1;
}
static void raw_rejections(void)
{
    const mirror_native_backend*n=mirror_camera_native();assert(n->readout_flags);
    sensor=malloc(n->sensor_bytes);assert(sensor);memset(sensor,0x5a,n->sensor_bytes);
    const unsigned errors[]={MG_READOUT,MG_READOUT,MG_READOUT,MG_READOUT,MG_READOUT,
        MG_CONTEXT,MG_CONTEXT,MG_NO_SHUTTER,MG_NO_SHUTTER,MG_READOUT,
        MG_OVERLAP,MG_CANCEL,MG_SHUTDOWN,MG_READOUT,MG_NO_SHUTTER,MG_CANCEL};
    /* Shutdown closes the backend permanently, so run it after the other cases. */
    for(unsigned i=0;i<16;i++)if(i!=12)rejected_capture(i,errors[i]);
    rejected_capture(12,errors[12]);
    unsigned reads=hardware_reads,patches=hooks;
    mirror_gate_automatic(1);mirror_gate_service();mirror_gate_full_press();
    assert(hardware_reads==reads&&hooks==patches);
    free(sensor);sensor=0;
    puts("70D main capture guards: 16 layout/context/latch/overlap/cancel/shutdown/workspace/re-enable rejections: PASS");
}
static unsigned sample(const uint8_t*row,unsigned x)
{
    unsigned bit=x*14,offset=bit%16;row+=(bit/16)*2;
    unsigned first=row[0]|((unsigned)row[1]<<8);
    if(offset<=2)return (first>>(2-offset))&16383;
    unsigned second=row[2]|((unsigned)row[3]<<8);
    return (((first<<16)|second)>>(18-offset))&16383;
}
static unsigned reflected(unsigned at,unsigned begin,unsigned end,unsigned divisor,unsigned low,unsigned high)
{
    unsigned size=2*((end-begin)/2/divisor),v=at;
    if(low&&at<begin+size)v=2*(begin+size-1)-at;
    else if(high&&at>=end-size)v=2*(end-size)-at;
    assert(v>=begin&&v<end&&((v^at)&1)==0);
    return v;
}
static unsigned expected_sample(const uint8_t*original,unsigned x,unsigned y,const mirror_native_backend*n,unsigned mask,unsigned dx,unsigned dy)
{
    if(x<n->region[1]||x>=n->region[3]||y<n->region[0]||y>=n->region[2])return sample(original+y*n->pitch,x);
    unsigned sx=reflected(x,n->region[1],n->region[3],dx,mask&1,mask&2);
    unsigned sy=reflected(y,n->region[0],n->region[2],dy,mask&4,mask&8);
    return sample(original+sy*n->pitch,sx);
}
static void raw_transport(void)
{
    const mirror_native_backend*n=mirror_camera_native();assert(n);
    sensor=malloc(n->sensor_bytes);uint8_t*original=malloc(n->sensor_bytes);assert(sensor&&original);
    for(unsigned i=0;i<n->sensor_bytes;i++)original[i]=(uint8_t)((i*37)^(i>>7));
    fake_xa=fake_xb=n->pitch;fake_xn=n->readout_xn;fake_off1=0;fake_flags=n->readout_flags;
    const unsigned masks[]={1,2,4,8,3,12,15};unsigned count=0;
    for(unsigned k=0;k<7;k++)for(unsigned dx=2;dx<=6;dx++)for(unsigned dy=2;dy<=6;dy++){
        unsigned mask=masks[k];
        if(!(mask&3)&&dx!=2)continue;
        if(!(mask&12)&&dy!=2)continue;
        if((mask&3)==3&&dx==2)continue;
        if((mask&12)==12&&dy==2)continue;
        lv=1;lens_info.job_state=0;controls=(fx_params){{FX_MIRROR_EDGES,mask,dx,dy}};
        mirror_gate_automatic(0);mirror_gate_automatic(1);mirror_gate_service();
        mirror_gate_full_press();memcpy(sensor,original,n->sensor_bytes);
        uint32_t saved[16]={0};uint32_t*regs=saved+1;
        saved[0]=0x13;regs[0]=SOURCE;regs[10]=n->stage_context;regs[13]=n->stage_caller;
        lv=0;lens_info.job_state=1;stage_callback(regs,regs+14,n->stage_pc);
        mirror_gate_report r;mirror_gate_status(&r);assert(r.phase==MG_DONE&&r.patch_done&&r.patch_verified==896&&!r.patch_mismatches);
        assert(!scratch_held);
        for(unsigned y=0;y<n->height;y++)for(unsigned x=0;x<n->width;x++){
            assert(sample(sensor+y*n->pitch,x)==expected_sample(original,x,y,n,mask,dx,dy));
        }
        count++;
    }
    assert(count==44);free(sensor);free(original);sensor=0;
    printf("%s native hook transport: 44 full-size RAW layouts and unchanged margins: PASS (registered CFA reference)\n",mirror_camera_name());
}
static void select_camera(const char*m,const char*f){model=m;firmware=f;}
static void check_no_capture(void)
{
    unsigned reads=hardware_reads,patches=hooks,rom=rom_reads;
    mirror_dma_info info;memset(&info,0x5a,sizeof(info));mirror_dma_info old=info;
    assert(!mirror_camera_native());assert(!mirror_camera_dma(0,&info));assert(!memcmp(&old,&info,sizeof(info)));
    assert(!mirror_gate_request());assert(!mirror_gate_request_source());assert(!mirror_gate_request_patch());assert(!mirror_gate_request_full());
    assert(!mirror_raw_trace_request());mirror_raw_trace_runtime();mirror_gate_automatic(1);
    mirror_gate_full_press();mirror_gate_reader(0xff1707e8);mirror_gate_service();mirror_raw_trace_service();
    assert(hardware_reads==reads&&hooks==patches&&rom_reads==rom);
}
int main(int argc,char **argv)
{
    check_no_capture();
    const char *candidates[][2]={
        {"5D2","2.1.2"},{"5D3","1.1.3"},{"5D3","1.2.3"},{"6D","1.1.6"},
        {"7D","2.0.3"},{"50D","1.0.9"},{"60D","1.1.1"},{"70D","1.1.2"},
        {"100D","1.0.1"},{"550D","1.0.9"},{"600D","1.0.2"},{"650D","1.0.4"},
        {"700D","1.1.5"},{"1100D","1.0.5"},
    };
    for(unsigned i=0;i<sizeof(candidates)/sizeof(candidates[0]);i++){
        select_camera(candidates[i][0],candidates[i][1]);assert(mirror_select_camera());
        assert(!strcmp(mirror_camera_name(),model));
#ifdef MIRROR_70D_RESEARCH
        if(!strcmp(model,"70D"))assert(mirror_camera_native());else
#endif
        check_no_capture();
        select_camera(candidates[i][0],"9.9.9");assert(!mirror_select_camera());check_no_capture();
    }
    select_camera("EOSM","2.0.2");assert(mirror_select_camera());assert(mirror_camera_native());
    const mirror_native_backend*n=mirror_camera_native();
    assert(n->stage_pc==0xff3608d8&&n->sensor_bytes==n->height*n->pitch);
    assert(n->region[2]<=n->height&&n->region[3]<=n->width);
    /* IMG_9987.CR2 exposes 5208x3476 at (72,52), as also specified by
     * LibRaw's EOS M table. Canon's smaller JPEG crop leaves visible RAW
     * strips of 12/12/8/12 pixels untouched with the old rectangle. */
    const uint32_t decoded_region[]={52,72,3528,5280};
    assert(!memcmp(n->region,decoded_region,sizeof(decoded_region)));
    fake_xa=(2u<<16)|9240;fake_xb=(3u<<16)|9240;fake_xn=(4u<<16)|3528;fake_off1=0x7ffff;
    mirror_dma_info q;assert(mirror_camera_dma(0,&q));
    assert(q.xa==9240&&q.ya==2&&q.xb==9240&&q.yb==3&&q.xn==3528&&q.yn==4&&q.off1a==UINT32_MAX);
    unsigned reads=hardware_reads;assert(!mirror_camera_dma(0,0));assert(!mirror_camera_dma(32,&q));assert(hardware_reads==reads);
    select_camera("EOSM","2.0.3");assert(!mirror_select_camera());check_no_capture();
    select_camera("R5","1.0.0");assert(!mirror_select_camera());check_no_capture();
    select_camera("1300D","1.1.0");assert(!mirror_select_camera());check_no_capture();
    select_camera("EOSM","2.0.2");assert(mirror_select_camera());
#ifdef MIRROR_70D_RESEARCH
    if(argc>1&&(!strcmp(argv[1],"70d")||!strcmp(argv[1],"70d-guards"))){
        select_camera("70D","1.1.2");assert(mirror_select_camera());n=mirror_camera_native();
        assert(n&&n->point_count==5&&n->stage_job_offset==0xac&&n->readout_flags==0x20000000&&n->readout_xn==3719);
    }
#endif
    bad_rom=argc>1&&!strcmp(argv[1],"bad-rom")?1:argc>1&&!strcmp(argv[1],"bad-stage")?2:0;
    mirror_gate_automatic(1);mirror_raw_trace_service();mirror_gate_service();
    mirror_gate_report gate;mirror_gate_status(&gate);mirror_raw_trace_report trace;mirror_raw_trace_status(&trace);
    if(bad_rom){assert(trace.phase==MT_FAILED&&trace.error==MT_GUARD&&hooks==0);assert(gate.phase==MG_FAILED);assert(rom_reads==(bad_rom==1?36u:1u));}
    else{
        assert(hooks==n->point_count+1&&stage_callback&&gate.phase==MG_ARMED);
        if(argc>1&&!strcmp(argv[1],"70d-guards")){raw_rejections();return 0;}
        if(argc>1&&(!strcmp(argv[1],"raw")||!strcmp(argv[1],"70d"))){raw_transport();return 0;}
        uint32_t saved[16]={0};uint32_t*regs=saved+1;unsigned reads_before=hardware_reads;
        /* No shutter/context: the hook must reject before dereferencing Canon memory. */
        stage_callback(regs,regs+14,n->stage_pc);mirror_gate_status(&gate);
        assert(gate.phase==MG_FAILED&&gate.error==MG_CONTEXT&&hardware_reads==reads_before);
    }
    assert(fx_preview_geometry(720,480,1440));assert(fx_preview_geometry(720,240,1440));
    assert(!fx_preview_geometry(1920,1080,3840));assert(!fx_preview_geometry(736,480,1472));
    assert(!fx_preview_geometry(720,480,1439));assert(!fx_preview_geometry(-1,480,1440));
    assert(!fx_preview_geometry(540,480,1080));assert(!fx_preview_geometry(720,320,1440));
    puts(bad_rom?"Camera guards and ROM mismatch: PASS":"Camera guards, scalar DMA and capture rejection: PASS");return 0;
}
