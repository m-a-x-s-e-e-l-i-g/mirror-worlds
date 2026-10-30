/* Actual preview/gate/RAW code with an SDK fixture, not Canon timing proof. */
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include "fx_sdk.h"
#include "mirror_camera_sdk.h"
#include "mirror_trace_sdk.h"
#include "mirror_camera.h"
#include "mirror_capture_gate.h"
#include "mirror_raw_trace.h"
extern unsigned preview_test_clock,allocations;
extern int menu_shown;
extern int preview_test_half;
extern void (*preview_test_commit_hook)(void);
static fx_capture_scratch *painting_lease;
static void while_painting(void){assert(painting_lease&&!fx_capture_scratch_ready(painting_lease));}
int gui_state;
struct test_lens lens_info;
static unsigned hooks;
static uint8_t *sensor;
static void (*stage)(uint32_t*,uint32_t*,uint32_t);
static unsigned plan_action,write_action;
#ifndef FX_REGISTERED_TEST_HOOK
#error This integration fixture requires the actual RAW preflight/write hooks
#endif
void FX(registered_plan_hook)(void)
{
    unsigned action=plan_action;plan_action=0;
    if(action==1)mirror_gate_cancel();
    if(action==2){mirror_gate_shutdown();fx_stop();fx_service();assert(allocations);}
}
void FX(registered_write_hook)(void)
{
    if(write_action){
        write_action=0;mirror_gate_cancel();fx_stop();fx_service();assert(allocations);
        fx_capture_scratch unavailable={0};assert(!fx_capture_scratch_acquire(&unavailable));
    }
}
#define SOURCE 0x01000000u
#define JOB 0x00200000u
int is_camera(const char*m,const char*f){return !strcmp(m,"EOSM")&&!strcmp(f,"2.0.2");}
unsigned get_us_clock(void){return preview_test_clock*1000;}
void msleep(unsigned ms){preview_test_clock+=ms;}
int get_current_task_id(void){return 1;}
uint32_t edmac_get_base(uint32_t c){(void)c;return 0xc0f04000;}
uint32_t edmac_get_state(uint32_t c){(void)c;return 0;}
uint32_t edmac_get_flags(uint32_t c){(void)c;return mirror_camera_native()->readout_flags;}
uint32_t edmac_get_address(uint32_t c){(void)c;return SOURCE+mirror_camera_native()->readout_offset;}
uint32_t edmac_get_pointer(uint32_t c){(void)c;return SOURCE+mirror_camera_native()->readout_offset+mirror_camera_native()->readout_bytes;}
uint32_t shamem_read(uint32_t address)
{
    const mirror_native_backend*n=mirror_camera_native();
    switch(address&255){case 0x14:case 0x10:return n->pitch;case 0xc:return n->readout_xn;default:return 0;}
}
uint32_t mirror_trace_test_read32(uint32_t address)
{assert(address==mirror_camera_native()->stage_context+mirror_camera_native()->stage_job_offset);return JOB;}
uint16_t mirror_trace_test_read16(uint32_t address)
{
    const mirror_native_backend*n=mirror_camera_native();
    unsigned offset=(address&~n->alias_bit)-SOURCE-n->origin_offset;
    assert(sensor&&offset+1<n->sensor_bytes);return sensor[offset]|((unsigned)sensor[offset+1]<<8);
}
void *mirror_trace_test_sensor_pointer(uint32_t address)
{
    const mirror_native_backend*n=mirror_camera_native();
    assert(address==((SOURCE+n->origin_offset)|n->alias_bit));return sensor;
}
uint32_t read_value(uint8_t*address,int instruction)
{
    const mirror_native_backend*n=mirror_camera_native();unsigned a=(unsigned)(uintptr_t)address;assert(instruction);
    for(unsigned i=0;i<n->point_count;i++)for(unsigned j=0;j<4;j++)if(a==n->points[i].pc+j*4)return n->points[i].words[j];
    for(unsigned j=0;j<4;j++)if(a==n->stage_pc+j*4)return n->stage_words[j];
    assert(!"unknown hook ROM address");return 0;
}
int patch_hook_function(uintptr_t address,uint32_t instruction,void(*callback)(uint32_t*,uint32_t*,uint32_t),const char*description)
{(void)instruction;(void)description;hooks++;if(address==mirror_camera_native()->stage_pc)stage=callback;return 0;}
static void fresh(struct display_filter_buffers*b)
{fx_state state;assert(fx_filter(0));fx_filter(b);assert(fx_delivered_state(&state));}
static void arm(struct display_filter_buffers*b)
{
    mirror_gate_automatic(0);fresh(b);mirror_gate_automatic(1);mirror_raw_trace_service();mirror_gate_service();
    mirror_gate_report r;mirror_gate_status(&r);assert(r.phase==MG_ARMED&&!r.latched);
}
static void shoot(const mirror_native_backend*n)
{
    lv=0;lens_info.job_state=1;
    uint32_t saved[16]={0};uint32_t*regs=saved+1;
    saved[0]=0x13;regs[0]=SOURCE;regs[10]=n->stage_context;regs[13]=n->stage_caller;
    assert(stage&&hooks==n->point_count+1);stage(regs,regs+14,n->stage_pc);
}
static void fill_sensor(const mirror_native_backend*n)
{for(unsigned i=0;i<n->sensor_bytes;i++)sensor[i]=(uint8_t)((i*37)^(i>>7));}
static void unchanged_sensor(const mirror_native_backend*n)
{for(unsigned i=0;i<n->sensor_bytes;i++)assert(sensor[i]==(uint8_t)((i*37)^(i>>7)));}
int main(int argc,char**argv)
{
    (void)argv;
    assert(mirror_select_camera());const mirror_native_backend*n=mirror_camera_native();
    fx_camera_init();assert(fx_native_capture_mode());assert(fx_capture_scratch_configure(2*n->pitch));fx_canon_gui(0);assert(fx_start());
    fx_params params={{180,2,2,2}};assert(fx_controls(&params));fx_service();
    size_t bytes=1440*480;uint8_t*src=malloc(bytes),*dst=malloc(bytes);assert(src&&dst);
    for(unsigned i=0;i<bytes;i++)src[i]=(uint8_t)((i*37)^(i>>7));
    struct display_filter_buffers buffers={src,dst};fresh(&buffers);
    /* RAW scratch lives after the canvas: a held lease must not stop or be
     * overwritten by continued preview rendering while autofocus is held. */
    fx_capture_scratch tail={0};assert(fx_capture_scratch_acquire(&tail));
    assert(tail.size==2*n->pitch);memset(tail.data,0x6d,tail.size);
    painting_lease=&tail;preview_test_commit_hook=while_painting;fresh(&buffers);preview_test_commit_hook=NULL;
    assert(fx_capture_scratch_ready(&tail));
    for(size_t i=0;i<tail.size;i++)assert(((uint8_t*)tail.data)[i]==0x6d);
    assert(fx_capture_scratch_release(&tail));assert(!fx_capture_scratch_ready(&tail));fresh(&buffers);
    arm(&buffers);preview_test_half=1;mirror_gate_half_press(1);
    mirror_gate_report half;mirror_gate_status(&half);assert(half.latched);
    unsigned first=half.full_ms;preview_test_clock+=6000;fresh(&buffers);mirror_gate_service();
    mirror_gate_status(&half);assert(half.phase==MG_ARMED&&half.latched&&half.full_ms>first);
    preview_test_half=0;mirror_gate_half_press(0);preview_test_clock+=5001;mirror_gate_service();
    mirror_gate_status(&half);assert(half.phase==MG_ARMED&&!half.latched&&!half.error);
    int *modes[]={&ext_monitor_hdmi,&lv_dispsize,&lv_paused,&menu_shown,&vram_lv.height};
    const int invalid[]={1,5,1,1,240};
    for(unsigned i=0;i<5;i++){
        arm(&buffers);int old=*modes[i];*modes[i]=invalid[i];mirror_gate_full_press();
        mirror_gate_report r;mirror_gate_status(&r);assert(r.phase==MG_ARMED&&!r.latched);
        *modes[i]=old;mirror_gate_full_press();mirror_gate_status(&r);assert(!r.latched);
        fresh(&buffers);mirror_gate_full_press();mirror_gate_status(&r);assert(r.latched&&!memcmp(&r.params,&params,sizeof(params)));
    }
    arm(&buffers);fx_canon_gui(1);fx_canon_gui(0);mirror_gate_full_press();
    mirror_gate_report r;mirror_gate_status(&r);assert(!r.latched);
    fresh(&buffers);mirror_gate_full_press();mirror_gate_status(&r);assert(r.latched);
    fx_capture_scratch unavailable={0};assert(!fx_capture_scratch_acquire(&unavailable));
    /* A missed hook times out and releases the borrowed preview canvas. */
    preview_test_clock+=5001;mirror_gate_service();mirror_gate_status(&r);assert(r.phase==MG_FAILED&&r.error==MG_NO_SHUTTER);
    arm(&buffers);mirror_gate_full_press();mirror_gate_status(&r);assert(r.latched);
    assert(!fx_capture_scratch_acquire(&unavailable));
    sensor=malloc(n->sensor_bytes);assert(sensor);
    fill_sensor(n);
    /* Cancel after the primitive has validated its workspace, immediately before
     * its last cancellation check. No packed source byte may change. */
    plan_action=1;shoot(n);mirror_gate_status(&r);
    assert(r.phase==MG_FAILED&&r.error==MG_CANCEL&&!r.patch_started&&!r.patch_done);unchanged_sensor(n);
    lv=1;lens_info.job_state=0;arm(&buffers);
    /* EOS M's supported half-shutter event, then quick physical release.
     * No full-shutter GUI callback is dispatched on this successful shot. */
    preview_test_half=1;mirror_gate_half_press(1);preview_test_half=0;mirror_gate_half_press(0);
    /* A valid physical-edge latch survives Canon leaving LV for this shot. */
    lv=0;lens_info.job_state=1;fx_state state;assert(!fx_delivered_state(&state));
    shoot(n);
    mirror_gate_status(&r);assert(r.phase==MG_DONE&&!r.error&&r.patch_done&&r.patch_verified==896&&!r.patch_mismatches&&r.patch_changed);
    assert(!memcmp(&r.params,&params,sizeof(params)));
    uint8_t*expected=malloc(n->sensor_bytes);assert(expected);memcpy(expected,sensor,n->sensor_bytes);
    /* Callback completion releases the lease; a fresh frame is needed before
     * acquisition, never the old canvas contents used as RAW workspace. */
    assert(!fx_capture_scratch_acquire(&unavailable));lv=1;lens_info.job_state=0;fresh(&buffers);
    assert(fx_capture_scratch_acquire(&unavailable));assert(fx_capture_scratch_release(&unavailable));
    arm(&buffers);mirror_gate_full_press();fill_sensor(n);write_action=1;shoot(n);mirror_gate_status(&r);
    assert(r.phase==MG_FAILED&&r.error==MG_CANCEL&&r.patch_done&&r.patch_verified==896&&!r.patch_mismatches);
    assert(!memcmp(sensor,expected,n->sensor_bytes));fx_service();assert(!allocations);
    lv=1;lens_info.job_state=0;assert(fx_start());fx_service();arm(&buffers);mirror_gate_full_press();mirror_gate_status(&r);assert(r.latched);
    if(argc>1){
        fill_sensor(n);plan_action=2;shoot(n);mirror_gate_status(&r);
        assert(r.phase==MG_FAILED&&r.error==MG_SHUTDOWN&&!r.patch_started&&!r.patch_done);unchanged_sensor(n);
    }else{
        fx_stop();fx_service();assert(allocations); /* Lease keeps arena alive. */
        mirror_gate_shutdown();
    }
    fx_stop();fx_service();assert(!allocations);
    free(expected);free(sensor);free(src);free(dst);
    puts("Preview-to-RAW integration: stale mode/review latches refused; fresh EOS M latch survives Canon LV exit: PASS");
    puts("Registered capture workspace: missed-hook timeout, completion, cancel/rearm and shutdown release; stop retains active lease: PASS");
    puts("RAW cancellation boundary: pre-write source unchanged; post-write complete frame and retained workspace: PASS");
    puts("EOS M half-shutter: continued preview, long focus hold, quiet release and capture without full-GUI event: PASS");
}
