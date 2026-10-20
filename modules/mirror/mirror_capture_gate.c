/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#include <string.h>
#ifdef FX_GATE_HOST_TEST
#include "mirror_trace_sdk.h"
#define READ32(a) mirror_trace_test_read32(a)
#define READ16(a) mirror_trace_test_read16(a)
#define SENSOR_PTR(a) mirror_trace_test_sensor_pointer(a)
#else
#include <module.h>
#include <dryos.h>
#include <lens.h>
#include <edmac.h>
#include <patch.h>
#include <tasks.h>
#define READ32(a) (*(const volatile uint32_t*)(uintptr_t)(a))
#define READ16(a) (*(const volatile uint16_t*)(uintptr_t)(a))
#define SENSOR_PTR(a) ((void*)(uintptr_t)(a))
#endif
#include "mirror_capture_gate.h"
#include "mirror_raw_trace.h"
#include "gl_format.h"
#include "fx_mirror_raw.h"
#include "fx_mirror_edges.h"
#include "fx_mirror_sensor.h"
#define STAGE_PC 0xff3608d8u
#define STAGE_CONTEXT 0x3f3d4u
static const uint32_t stage_words[4]={0xe12fff1eu,0xe3a00000u,0xe12fff1eu,0xe12fff1eu};
static struct {
    mirror_gate_report r;
    uint16_t samples[64*14]; /* First pass, kept out of UI/status stack copies. */
    uint16_t patch_before[64*14],patch_expected[64*14],patch_after[64*14];
    fx_mirror_raw patch_map; /* Avoid a large new frame on Canon's task stack. */
    unsigned installed,closed,cancel,log_pending,writing,automatic;
} gate;
static unsigned lock(void){unsigned s=cli();__asm__ __volatile__("" ::: "memory");return s;}
static void unlock(unsigned s){__asm__ __volatile__("" ::: "memory");sei(s);}
static unsigned canonical(unsigned v){v&=~0x40000000u;return v>=0x1000u&&v<0x20000000u?v:0;}
static void finish_locked(unsigned error)
{gate.r.error=error;gate.r.phase=error?MG_FAILED:MG_DONE;gate.log_pending=!gate.closed&&!gate.automatic;}
void mirror_gate_status(mirror_gate_report*out)
{if(out){unsigned s=lock();*out=gate.r;out->installed=gate.installed;unlock(s);}}
static int request(unsigned sample_mode)
{
    unsigned s=lock();
    if(gate.closed||gate.r.phase==MG_QUEUED||gate.r.phase==MG_ARMED||gate.r.phase==MG_HELD||gate.log_pending||gate.writing){unlock(s);return 0;}
    memset(&gate.r,0,sizeof(gate.r));memset(gate.samples,0,sizeof(gate.samples));gate.r.sample_mode=sample_mode;gate.cancel=0;gate.r.requested_ms=get_ms_clock();
    memset(gate.patch_before,0,sizeof(gate.patch_before));memset(gate.patch_expected,0,sizeof(gate.patch_expected));memset(gate.patch_after,0,sizeof(gate.patch_after));
    gate.r.phase=MG_QUEUED;unlock(s);
    if(!gate.automatic&&!mirror_raw_trace_request()){s=lock();finish_locked(MG_TRACE_BUSY);unlock(s);return 0;}
    return 1;
}
void mirror_gate_automatic(unsigned enabled)
{
    unsigned s=lock();
    if(!enabled){unlock(s);mirror_gate_cancel();s=lock();gate.automatic=0;gate.log_pending=0;unlock(s);return;}
    if(!gate.automatic&&!gate.closed){
        gate.automatic=1;gate.cancel=0;gate.log_pending=0;
        if(gate.r.phase!=MG_HELD){memset(&gate.r,0,sizeof(gate.r));}
    }
    unlock(s);
    if(gate.automatic)mirror_raw_trace_runtime();
}
int mirror_gate_request(void){return request(0);}
int mirror_gate_request_source(void){return request(1);}
int mirror_gate_request_patch(void){return request(2);}
int mirror_gate_request_full(void){return request(3);}
void mirror_gate_full_press(void)
{
    fx_state state;int ready=fx_delivered_state(&state);unsigned now=get_ms_clock(),s=lock();
    /* First edge owns this one-shot request; duplicates/held bursts cannot
     * replace its controls while the callback is preparing or yielding. */
    if(!gate.closed&&gate.r.phase==MG_ARMED&&!gate.r.latched&&ready){
        gate.r.latched=1;gate.r.full_ms=now;gate.r.preview_ms=state.last_ms;gate.r.params=state.params;
    }
    unlock(s);
}
void mirror_gate_cancel(void)
{
    unsigned s=lock();gate.cancel=1;
    if(gate.r.phase==MG_QUEUED||gate.r.phase==MG_ARMED)finish_locked(MG_CANCEL);
    unlock(s);
}
void mirror_gate_shutdown(void)
{
    unsigned s=lock();unsigned unfinished=gate.r.phase==MG_QUEUED||gate.r.phase==MG_ARMED||gate.log_pending||gate.writing;
    gate.closed=gate.cancel=1;gate.log_pending=0;
    if(unfinished)finish_locked(MG_SHUTDOWN);
    unlock(s); /* A held callback unwinds after its next reschedule. No unpatch. */
}
void mirror_gate_reader(unsigned pc)
{
    unsigned s=lock();
    if(!gate.closed&&gate.r.phase==MG_HELD){
        /* Conservative: every observed getter/setter or known compression
         * hook is a potential competing consumer, without pointer reads. */
        static const unsigned readers[]={0xff1707e8u,0xff1686d0u,0xff429210u,0xff4292b8u,
            0xff168128u,0xff429280u,0xff22dac0u,0xff22da74u};
        for(unsigned i=0;i<sizeof(readers)/sizeof(readers[0]);i++)if(pc==readers[i]){
            if(!gate.r.overlaps){gate.r.first_overlap_pc=pc;gate.r.first_overlap_us=get_us_clock();}
            gate.r.overlaps++;break;
        }
    }
    unlock(s);
}
/* Sensor origin is two rows before the QR readout address. This exact offset
 * is observed in both dev12/dev13 RAW reader10 configurations. Do not borrow
 * QR's shifted mosaic. The sampler reads only 1792 bytes from the existing
 * 32598720-byte nominal source, always through DIGIC V's uncached alias. */
static int photo_ready(const mirror_gate_report*r)
{
    struct edmac_info q=edmac_get_info(0);
    return !lv&&lens_info.job_state&&READ32(STAGE_CONTEXT+0xb4u)==r->job&&
        !edmac_get_state(0)&&!edmac_get_flags(0)&&
        canonical((unsigned)edmac_get_address(0))==canonical(r->source)+0x9060u&&
        canonical((unsigned)edmac_get_pointer(0))==canonical(r->source)+0x9060u+32607960u&&
        q.xa==9240&&q.xb==9240&&q.xn==3528&&!q.ya&&!q.yb&&!q.yn&&
        !q.off1a&&!q.off1b&&!q.off2a&&!q.off2b&&!q.off3;
}
static unsigned sample_pass(unsigned after)
{
    mirror_gate_report*r=&gate.r;unsigned began=get_us_clock();
    for(unsigned patch=0;patch<64;patch++){
        unsigned s=lock();
        unsigned error=gate.closed||ml_shutdown_requested?MG_SHUTDOWN:gate.cancel?MG_CANCEL:
            r->overlaps?MG_OVERLAP:get_us_clock()-r->enter_us>=250000u?MG_OVERRUN:
            !photo_ready(r)?MG_READOUT:MG_OK;
        unlock(s);if(error)return error;
        unsigned y=((patch/8)*1763/7)*2,x=((patch%8)*659/7)*8;
        unsigned base=(canonical(r->source)+0x4830u)|0x40000000u;
        for(unsigned row=0;row<2;row++)for(unsigned word=0;word<7;word++){
            unsigned index=patch*14+row*7+word;
            uint16_t value=READ16(base+(y+row)*9240u+x*14u/8u+word*2u);
            if(after){r->changed+=value!=gate.samples[index];r->after_count++;}
            else{gate.samples[index]=value;r->before_count++;}
        }
    }
    unsigned elapsed=get_us_clock()-began;
    if(after)r->sample_after_us=elapsed;else r->sample_before_us=elapsed;
    return after&&r->changed?MG_SOURCE:MG_OK;
}
static unsigned patch_guard(void)
{
    unsigned s=lock();mirror_gate_report*r=&gate.r;
    unsigned error=gate.closed||ml_shutdown_requested?MG_SHUTDOWN:gate.cancel?MG_CANCEL:
        r->overlaps?MG_OVERLAP:get_us_clock()-r->enter_us>=150000u?MG_OVERRUN:
        !photo_ready(r)?MG_READOUT:MG_OK;
    unlock(s);return error;
}
static const uint32_t*patch_region(void)
{
    static const uint32_t small[4]={1536,2160,2048,3184},full[4]={64,84,3520,5268};
    return gate.r.sample_mode==3?full:small;
}
static void patch_position(unsigned patch,unsigned*y,unsigned*x)
{
    if(gate.r.sample_mode==3){*y=64+((patch/8)*1727/7)*2;*x=88+((patch%8)*646/7)*8;}
    else{*y=1536+((patch/8)*255/7)*2;*x=2160+((patch%8)*127/7)*8;}
}
static unsigned patch_test(void)
{
    mirror_gate_report*r=&gate.r;fx_mirror_raw*m=&gate.patch_map;
    unsigned base=(canonical(r->source)+0x4830u)|0x40000000u;
    const fx_params fixed={{90,2,500,500}};
    if(memcmp(&r->params,&fixed,sizeof(fixed))&&!fx_edges_valid(&r->params))return MG_CONTROLS;
    const uint32_t*region=patch_region();
    gl_frame frame={SENSOR_PTR(base),32598720u,5280,3528,9240,GL_CANON14,0,16383};
    if(fx_mirror_raw_prepare(m,&frame,region,&r->params,0))return MG_PATCH_PREP;
    for(unsigned patch=0;patch<64;patch++){
        unsigned error=patch_guard();if(error)return error;
        unsigned y,x;patch_position(patch,&y,&x);
        for(unsigned row=0;row<2;row++){
            uint16_t v[8];
            for(unsigned i=0;i<8;i++)if(fx_mirror_raw_sample(m,x+i,y+row,&v[i]))return MG_PATCH_PREP;
            for(unsigned j=0;j<7;j++){
                unsigned n=patch*14+row*7+j;
                gate.patch_before[n]=READ16(base+(y+row)*9240u+x*14u/8u+j*2u);
                unsigned expected=j<6?((unsigned)v[j]<<(2+2*j))|(v[j+1]>>(12-2*j)):((unsigned)v[6]<<14)|v[7];
                gate.patch_expected[n]=(uint16_t)expected;
                r->patch_changed+=gate.patch_before[n]!=gate.patch_expected[n];
            }
        }
    }
    unsigned error=patch_guard();if(error)return error;
    /* No yield or early cancellation once the bounded rectangle starts.
     * The fixed source area remains unchanged; the complete fold is idempotent.
     * This is an opt-in publication experiment, NOT a general ownership grant. */
    unsigned began=get_us_clock();r->patch_started=1;
    int result=fx_mirror_sensor_axial(m,SENSOR_PTR(base),32598720u);
#ifndef FX_GATE_HOST_TEST
    unsigned zero=0;__asm__ __volatile__("mcr p15, 0, %0, c7, c10, 4"::"r"(zero):"memory");
#endif
    r->patch_us=get_us_clock()-began;r->patch_done=!result;
    if(result)return MG_PATCH_PREP;
    /* Read back via the same uncached alias. No global cache clean can publish
     * potentially stale dirty sensor lines over these writes. Later consumers
     * and the saved CR2 must be tested independently on the actual camera. */
    for(unsigned patch=0;patch<64;patch++){
        unsigned y,x;patch_position(patch,&y,&x);
        for(unsigned row=0;row<2;row++)for(unsigned j=0;j<7;j++){
            unsigned n=patch*14+row*7+j;
            gate.patch_after[n]=READ16(base+(y+row)*9240u+x*14u/8u+j*2u);
            r->patch_mismatches+=gate.patch_after[n]!=gate.patch_expected[n];r->patch_verified++;
        }
    }
    return r->patch_mismatches?MG_PATCH_VERIFY:MG_OK;
}
static void enter(uint32_t*regs,uint32_t*stack,uint32_t pc)
{
    unsigned s=lock();
    if(gate.closed||gate.r.phase!=MG_ARMED){unlock(s);return;}
    if(!regs||stack!=regs+14||pc!=STAGE_PC){finish_locked(MG_CONTEXT);unlock(s);return;}
    mirror_gate_report*r=&gate.r;
    r->enter_us=get_us_clock();r->cpsr=regs[-1];r->lr=regs[13];r->context=regs[10];r->source=regs[0];
    /* Only the exact, source-backed synchronous caller, not an interrupt or
     * another caller of the no-op, may run this scheduling experiment. */
    if((r->cpsr&31u)!=0x13u||(r->cpsr&0xc0u)||r->lr!=0xff152238u||r->context!=STAGE_CONTEXT){
        finish_locked(MG_CONTEXT);unlock(s);return;
    }
    r->task=(unsigned)get_current_task_id();r->job=READ32(STAGE_CONTEXT+0xb4u);
    if(!r->latched||get_ms_clock()-r->full_ms>5000u){finish_locked(MG_NO_SHUTTER);unlock(s);return;}
    r->dma_before=edmac_get_state(0);r->dma_address=(unsigned)edmac_get_address(0);r->dma_pointer=(unsigned)edmac_get_pointer(0);
    unsigned flags=edmac_get_flags(0);struct edmac_info q=edmac_get_info(0);r->dma_after=edmac_get_state(0);
    unsigned source=canonical(r->source),address=canonical(r->dma_address),pointer=canonical(r->dma_pointer);
    if(!source||source>0x20000000u-0x9060u-32607960u||!canonical(r->job)||
       lv||!lens_info.job_state||r->dma_before||r->dma_after||flags||
       address!=source+0x9060u||pointer!=address+32607960u||q.xa!=9240||q.xb!=9240||q.xn!=3528||
       q.ya||q.yb||q.yn||q.off1a||q.off1b||q.off2a||q.off2b||q.off3){finish_locked(MG_READOUT);unlock(s);return;}
    r->phase=MG_HELD;unsigned began=r->enter_us;unlock(s);
    unsigned sample_error=r->sample_mode?sample_pass(0):MG_OK;
    /* Before either opt-in mutation, use the same scheduling/sample check. Yield so
     * lower-priority consumers can run; a CPU spin would mask a missing hold.
     * 100ms is requested, not an OS rescheduling guarantee. Twenty yield calls
     * cap iterations; actual elapsed time and overruns are reported. */
    for(unsigned i=0;i<20;i++){
        s=lock();unsigned stop=sample_error||gate.closed||gate.cancel||ml_shutdown_requested||r->overlaps||get_us_clock()-began>=100000u;
        unlock(s);if(stop)break;
        msleep(5);s=lock();r->sleeps++;unlock(s);
    }
    if(r->sample_mode&&!sample_error)sample_error=sample_pass(1);
    if(r->sample_mode>=2&&!sample_error)sample_error=patch_test();
    s=lock();r->release_us=get_us_clock();r->held_us=r->release_us-began;
    unsigned error=gate.closed||ml_shutdown_requested?MG_SHUTDOWN:gate.cancel?MG_CANCEL:r->overlaps?MG_OVERLAP:
        r->sample_mode&&!photo_ready(r)?MG_READOUT:
        sample_error?sample_error:r->held_us<100000u||r->held_us>(r->sample_mode==3?2000000u:250000u)?MG_OVERRUN:MG_OK;
    finish_locked(error);unlock(s);
    /* Original BX LR executes with Canon's original registers intact. A completed
     * experimental mutation is not a general lease or hard deadline proof. */
}
#ifndef MIRROR_RELEASE
static int text(FILE*f,const char*p)
{if(gate.closed||ml_shutdown_requested)return 0;size_t n=strlen(p);return FIO_WriteFile(f,p,n)==(int)n;}
static int sample_log_write(void)
{
    char path[64],line[256];uint32_t bytes;unsigned n;
    for(n=0;n<1000;n++){gl_snprintf(path,sizeof(path),"ML/LOGS/MSR%03u.LOG",n);if(FIO_GetFileSize(path,&bytes))break;}
    if(n==1000)return 0;
    FILE*f=FIO_CreateFile(path);if(!f)return 0;
    mirror_gate_report*r=&gate.r;
    int ok=text(f,"Mirror sensor source TEST v1 / EOSM202 / ML ed3e7c0\nRead-only uncached samples; no mirrored CR2 or ownership grant\n");
    gl_snprintf(line,sizeof(line),"gate=%s phase=%u error=%u source=%x job=%x origin_offset=4830 width=5280 height=3528 pitch=9240\n",r->log,r->phase,r->error,r->source,r->job);if(ok)ok=text(f,line);
    gl_snprintf(line,sizeof(line),"before_count=%u after_count=%u changed=%u before_us=%u after_us=%u\n",r->before_count,r->after_count,r->changed,r->sample_before_us,r->sample_after_us);if(ok)ok=text(f,line);
    /* Explicit words, independent of host byte order, no data-dependent string. */
    for(unsigned patch=0;ok&&patch<64;patch++){
        gl_snprintf(line,sizeof(line),"patch=%u y=%u x=%u words=",patch,((patch/8)*1763/7)*2,((patch%8)*659/7)*8);
        unsigned len=strlen(line);
        for(unsigned j=0;j<14;j++){gl_snprintf(line+len,sizeof(line)-len,"%04x",gate.samples[patch*14+j]);len+=4;}
        line[len++]='\n';line[len]=0;ok=text(f,line);
    }
    FIO_CloseFile(f);if(ok)gl_snprintf(r->sample_log,sizeof(r->sample_log),"%s",path);
    return ok;
}
static int patch_log_write(void)
{
    char path[64],line[320];uint32_t bytes;unsigned n;
    for(n=0;n<1000;n++){gl_snprintf(path,sizeof(path),"ML/LOGS/MPT%03u.LOG",n);if(FIO_GetFileSize(path,&bytes))break;}
    if(n==1000)return 0;
    FILE*f=FIO_CreateFile(path);if(!f)return 0;mirror_gate_report*r=&gate.r;
    int ok=text(f,r->sample_mode==3?"Mirror native mirror TEST v2 / EOSM202 / ML ed3e7c0\nExperimental ONE-shot full active image; centered 90/2 only\n":"Mirror native patch TEST v1 / EOSM202 / ML ed3e7c0\nExperimental ONE-shot rectangle; not full-frame native Mirror\n");
    gl_snprintf(line,sizeof(line),"gate=%s phase=%u error=%u source=%x job=%x origin_offset=4830 width=5280 height=3528 pitch=9240\n",r->log,r->phase,r->error,r->source,r->job);if(ok)ok=text(f,line);
    const uint32_t*region=patch_region();
    gl_snprintf(line,sizeof(line),"top=%u left=%u bottom=%u right=%u params=90,2,500,500\n",region[0],region[1],region[2],region[3]);if(ok)ok=text(f,line);
    gl_snprintf(line,sizeof(line),"started=%u done=%u transform_us=%u verified_words=%u mismatching_words=%u changed_expected_words=%u\n",r->patch_started,r->patch_done,r->patch_us,r->patch_verified,r->patch_mismatches,r->patch_changed);if(ok)ok=text(f,line);
    for(unsigned patch=0;ok&&patch<64;patch++){
        unsigned y,x;patch_position(patch,&y,&x);
        gl_snprintf(line,sizeof(line),"patch=%u y=%u x=%u",patch,y,x);
        unsigned len=strlen(line);
        const char*names[]={"before","expected","after"};const uint16_t*arrays[]={gate.patch_before,gate.patch_expected,gate.patch_after};
        for(unsigned k=0;k<3;k++){
            gl_snprintf(line+len,sizeof(line)-len," %s=",names[k]);len=strlen(line);
            for(unsigned j=0;j<14;j++){gl_snprintf(line+len,sizeof(line)-len,"%04x",arrays[k][patch*14+j]);len+=4;}
        }
        line[len++]='\n';line[len]=0;ok=text(f,line);
    }
    FIO_CloseFile(f);if(ok)gl_snprintf(r->sample_log,sizeof(r->sample_log),"%s",path);return ok;
}
static void log_write(void)
{
    char path[64],line[512];uint32_t bytes;unsigned n;
    if(!is_dir("ML/LOGS")&&FIO_CreateDirectory("ML/LOGS"))goto fail;
    for(n=0;n<1000;n++){gl_snprintf(path,sizeof(path),"ML/LOGS/MCG%03u.LOG",n);if(FIO_GetFileSize(path,&bytes))break;}
    if(n==1000)goto fail;
    FILE*f=FIO_CreateFile(path);if(!f)goto fail;
    mirror_gate_report*r=&gate.r;
    int ok=text(f,"Mirror capture scheduling TEST / EOSM202 / ML ed3e7c0\n");
    if(ok)ok=text(f,r->sample_mode==3?"Experimental full active-area mirror; max_hold_us=2000000\n":r->sample_mode==2?"Experimental mirrored sensor patch; restart removes hooks\n":r->sample_mode?"Read-only sensor samples; no owned RAW lease or mirrored CR2\n":"No sensor access or pixel changes; no owned RAW lease or mirrored CR2\n");
    gl_snprintf(line,sizeof(line),"phase=%u error=%u installed=%u core_error=%x requested_ms=%u armed_ms=%u requested_hold_us=100000\n",r->phase,r->error,gate.installed,r->core_error,r->requested_ms,r->armed_ms);if(ok)ok=text(f,line);
    gl_snprintf(line,sizeof(line),"latched=%u full_ms=%u preview_ms=%u params=%u,%u,%u,%u\n",r->latched,r->full_ms,r->preview_ms,r->params.value[0],r->params.value[1],r->params.value[2],r->params.value[3]);if(ok)ok=text(f,line);
    gl_snprintf(line,sizeof(line),"enter_us=%u release_us=%u held_us=%u sleeps=%u cpsr=%x lr=%x task=%x context=%x source=%x job=%x\n",r->enter_us,r->release_us,r->held_us,r->sleeps,r->cpsr,r->lr,r->task,r->context,r->source,r->job);if(ok)ok=text(f,line);
    gl_snprintf(line,sizeof(line),"dma_before=%u dma_after=%u dma_address=%x dma_pointer=%x overlaps=%u first_overlap_pc=%x first_overlap_us=%u\n",r->dma_before,r->dma_after,r->dma_address,r->dma_pointer,r->overlaps,r->first_overlap_pc,r->first_overlap_us);if(ok)ok=text(f,line);
    FIO_CloseFile(f);if(!ok)goto fail;
    gl_snprintf(gate.r.log,sizeof(gate.r.log),"%s",path);
    if(gate.r.sample_mode==1&&!sample_log_write())goto fail;
    if(gate.r.sample_mode>=2&&!patch_log_write())goto fail;
    return;
fail: if(!gate.closed){unsigned s=lock();gate.r.error=MG_LOG;gate.r.phase=MG_FAILED;unlock(s);}
}
#endif
void mirror_gate_service(void)
{
    if(ml_shutdown_requested||gate.closed){mirror_gate_shutdown();return;}
    if(gate.automatic&&(gate.r.phase==MG_IDLE||gate.r.phase==MG_DONE)&&
       !lens_info.job_state&&!get_halfshutter_pressed()&&lv&&!lv_paused&&!gui_menu_shown()&&
       gui_state!=1&&gui_state!=3&&gui_state!=12){
        fx_state state;
        if(fx_delivered_state(&state))request(3);
    }
    if(gate.r.phase==MG_QUEUED){
        mirror_raw_trace_report tr;mirror_raw_trace_status(&tr);
        unsigned s=lock();
        if(tr.phase==MT_FAILED)finish_locked(MG_TRACE_FAILED);
        else if(!gate.automatic&&get_ms_clock()-gate.r.requested_ms>15000u)finish_locked(MG_TIMEOUT);
        unlock(s);
        if(gate.r.phase==MG_QUEUED&&tr.phase==MT_ARMED&&tr.installed==255u&&
           !lens_info.job_state&&!get_halfshutter_pressed()&&lv&&!lv_paused&&!gui_menu_shown()){
            unsigned error=MG_OK;
            if(!gate.installed){
                for(unsigned j=0;j<4;j++)if(read_value((uint8_t*)(uintptr_t)(STAGE_PC+j*4),1)!=stage_words[j])error=MG_GUARD;
                if(!error&&(gate.closed||ml_shutdown_requested||gate.r.phase!=MG_QUEUED))error=gate.closed||ml_shutdown_requested?MG_SHUTDOWN:MG_CANCEL;
                if(!error){int result=patch_hook_function(STAGE_PC,stage_words[0],enter,"Mirror: capture scheduling TEST (restart removes)");
                    if(result){gate.r.core_error=(unsigned)result;error=MG_PATCH;}else gate.installed=1;}
            }
            s=lock();if(!gate.closed&&gate.r.phase==MG_QUEUED){
                if(error)finish_locked(error);else{gate.r.phase=MG_ARMED;gate.r.armed_ms=get_ms_clock();}}
            unlock(s);
        }
    }
    unsigned s=lock();
    if(!gate.automatic&&gate.r.phase==MG_ARMED&&get_ms_clock()-gate.r.armed_ms>60000u)finish_locked(MG_TIMEOUT);
    unsigned write=gate.log_pending&&!gate.writing&&!lens_info.job_state;
    if(write){gate.log_pending=0;gate.writing=1;}unlock(s);
#ifndef MIRROR_RELEASE
    if(write){log_write();s=lock();gate.writing=0;unlock(s);}
#else
    (void)write;
#endif
}
