/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade).
 * Patch ABI and TTL descriptor: pinned ML patch_cache.c / silent/lossless.c.
 * This diagnostic changes verified runtime instruction-cache entries only.
 * It never writes a sensor, Canon descriptor, arguments, file or property from
 * a hook. The normal Modules loader retains module code through shutdown. */
#include <string.h>
#ifdef FX_TRACE_HOST_TEST
#include "mirror_trace_sdk.h"
#define READ32(a) mirror_trace_test_read32(a)
#else
#include <module.h>
#include <dryos.h>
#include <lens.h>
#include <patch.h>
#include <menu.h>
#include <tasks.h>
#define READ32(a) (*(const volatile uint32_t*)(uintptr_t)(a))
#endif
#include "mirror_raw_trace.h"
#include "mirror_camera.h"
#include "mirror_capture_gate.h"
#include "gl_format.h"
#define NATIVE (*mirror_camera_native())
#define RAW_DESC NATIVE.raw_desc
#define SSS_DESC NATIVE.sss_desc
#define JPEG_DESC NATIVE.jpeg_desc
#define RAW_CONTEXT NATIVE.raw_context
#define SSS_CONTEXT NATIVE.sss_context
#define SLOTS 64u
#define points NATIVE.points
#define POINTS NATIVE.point_count
typedef struct {
    unsigned ms,us,kind,pc,lr,task,descriptor,source_field,effective_source;
    unsigned x,y,precision,rd_channel,rd_flags,rd_offset,wr_channel,output_suite,output2;
    unsigned gui,lv,job,context_job,opaque_context;
    unsigned dma_before,dma_after,dma_address,dma_pointer,dma_flags,xa,ya,xb,yb,xn,yn,off1a,off2a,off1b,off2b,off3;
    unsigned delivered,preview_ms;fx_params params;
    unsigned original_cpsr,argument_job,argument_source;
    unsigned reader_valid,reader_before,reader_after,reader_address,reader_pointer,reader_flags;
    mirror_dma_info reader;
} event;
static struct {
    mirror_raw_trace_report r;
#ifndef MIRROR_RELEASE
    event events[SLOTS];
#endif
    unsigned installed,active,closed,log_pending,writing,runtime;
} trace;
static unsigned lock(void){unsigned s=cli();__asm__ __volatile__("" ::: "memory");return s;}
static void unlock(unsigned s){__asm__ __volatile__("" ::: "memory");sei(s);}
static void end_locked(unsigned error)
{trace.active=0;trace.r.error=error;trace.r.phase=error?MT_FAILED:MT_DONE;trace.log_pending=!trace.runtime;}
static void end(unsigned error)
{unsigned s=lock();end_locked(error);unlock(s);}
void mirror_raw_trace_runtime(void)
{
    if(!mirror_camera_native())return;
    unsigned s=lock();trace.runtime=1;unlock(s);
    if(trace.r.phase!=MT_QUEUED&&trace.r.phase!=MT_ARMED)mirror_raw_trace_request();
}
int mirror_raw_trace_request(void)
{
    if(!mirror_camera_native())return 0;
    unsigned s=lock();
    if(trace.closed||trace.active||trace.r.phase==MT_QUEUED||trace.log_pending||trace.writing){unlock(s);return 0;}
    memset(&trace.r,0,sizeof(trace.r));trace.r.phase=MT_QUEUED;trace.r.requested_ms=get_ms_clock();
    unlock(s);return 1;
}
void mirror_raw_trace_status(mirror_raw_trace_report*out)
{if(out){unsigned s=lock();*out=trace.r;out->installed=trace.installed;unlock(s);}}
void mirror_raw_trace_cancel(void)
{if(trace.r.phase==MT_QUEUED||trace.r.phase==MT_ARMED)end(MT_CANCEL);}
void mirror_raw_trace_shutdown(void)
{
    unsigned s=lock();unsigned unfinished=trace.r.phase==MT_QUEUED||trace.r.phase==MT_ARMED||trace.log_pending||trace.writing;
    trace.closed=1;trace.active=0;trace.log_pending=0;
    if(unfinished){trace.r.phase=MT_FAILED;trace.r.error=MT_SHUTDOWN;}
    unlock(s);
    /* Never unpatch/recycle the core trampoline during a possible return.
     * The standard loader keeps this callback's code allocated until poweroff. */
}
static void observe(uint32_t*regs,uint32_t*stack,uint32_t pc)
{
    if(!mirror_camera_native())return;
    /* Gate overlap detection must remain live even if the metadata window
     * expires while another Canon task is inside the scheduling experiment. */
    mirror_gate_reader(pc);
#ifndef MIRROR_RELEASE
    /* Pinned patch_cache.c saves CPSR at regs[-1], original SP at regs+14.
     * Observe this saved context, never flags after callback code/cli(). */
    if(!trace.active||trace.closed||!regs||stack!=regs+14)return;
    unsigned began=get_us_clock(),s=lock();
    if(!trace.active||trace.closed){unlock(s);return;}
    unsigned kind=MT_KIND_COUNT;
    for(unsigned i=0;i<POINTS;i++)if(points[i].pc==pc)kind=points[i].kind;
    unsigned descriptor=kind==MT_RAW_SOURCE||kind==MT_JPEG_SOURCE?regs[6]:kind==MT_SSS_SOURCE?regs[7]:kind==MT_PREPARE?regs[1]:kind==MT_START||kind==MT_PREPARE_JPEG?regs[0]:0;
    unsigned accessor=kind==MT_JOB_GET||kind==MT_JOB_SET;
    unsigned binding=kind==MT_BINDING_ONLY;
    if(kind==MT_KIND_COUNT||(!accessor&&!binding&&descriptor!=RAW_DESC&&descriptor!=SSS_DESC&&descriptor!=JPEG_DESC)||
        (kind==MT_RAW_SOURCE&&(descriptor!=RAW_DESC||regs[5]!=RAW_CONTEXT))||
        (kind==MT_SSS_SOURCE&&(descriptor!=SSS_DESC||regs[6]!=SSS_CONTEXT))||
        (kind==MT_JPEG_SOURCE&&(descriptor!=JPEG_DESC||regs[7]!=SSS_CONTEXT))||
        (kind==MT_PREPARE_JPEG&&descriptor!=JPEG_DESC)){trace.r.skipped++;unlock(s);return;}
    unsigned index;
    if(trace.r.events<SLOTS)index=trace.r.events++;
    else{index=trace.r.dropped%SLOTS;trace.r.dropped++;}
    event*e=&trace.events[index];memset(e,0,sizeof(*e));
    e->ms=get_ms_clock();e->us=began;e->kind=kind;e->pc=pc;e->lr=regs[13];e->task=(unsigned)get_current_task_id();
    e->original_cpsr=regs[-1];
    e->descriptor=descriptor;
    /* Read fixed known descriptor/context storage ONLY. None of these pointer
     * values are dereferenced; RAW and output suites are just numbers here. */
    if(!accessor&&!binding){unsigned dimensions=READ32(descriptor+0x38);
    e->x=dimensions>>16;e->y=READ32(descriptor+0x3c)&65535;e->precision=READ32(descriptor+0x40);
    e->source_field=READ32(descriptor+0x58);
    e->effective_source=kind==MT_RAW_SOURCE||kind==MT_SSS_SOURCE||kind==MT_JPEG_SOURCE?regs[0]:e->source_field;
    e->rd_channel=READ32(descriptor+0x48);e->rd_flags=READ32(descriptor+0x50);e->rd_offset=READ32(descriptor+0x5c);
    e->wr_channel=READ32(descriptor+0x78);e->output_suite=READ32(descriptor+0x88);e->output2=READ32(descriptor+0xa0);
    unsigned context=descriptor==RAW_DESC?RAW_CONTEXT:SSS_CONTEXT,job_offset=descriptor==RAW_DESC?0x84:0x38;
    e->context_job=READ32(context+job_offset);e->opaque_context=READ32(context+(descriptor==RAW_DESC?0x88:0x44));
    }else if(accessor){
        /* Entry arguments ONLY, before Canon's tag check. No job/object or
         * source argument is dereferenced, and setter arguments stay intact. */
        e->argument_job=regs[0];
        if(kind==MT_JOB_SET)e->argument_source=e->effective_source=regs[1];
        e->context_job=regs[0];
    }else{
        /* Model-specific observation sites without an EOS M descriptor ABI.
         * Record the argument as a number only; never infer/dereference it. */
        e->argument_source=regs[0];
    }
    e->gui=(unsigned)gui_state;e->lv=(unsigned)lv;e->job=lens_info.job_state;
    e->dma_before=edmac_get_state(0);e->dma_address=(unsigned)edmac_get_address(0);e->dma_pointer=(unsigned)edmac_get_pointer(0);
    e->dma_flags=edmac_get_flags(0);
    mirror_dma_info info={0};mirror_camera_dma(0,&info);e->xa=info.xa;e->ya=info.ya;e->xb=info.xb;e->yb=info.yb;e->xn=info.xn;e->yn=info.yn;
    e->off1a=info.off1a;e->off2a=info.off2a;e->off1b=info.off1b;e->off2b=info.off2b;e->off3=info.off3;e->dma_after=edmac_get_state(0);
    /* Fixed observed reader channel only; never select a register bank from
     * an untrusted argument. At START these are configured, not yet started. */
    if(!accessor&&!binding&&e->rd_channel==10){
        e->reader_valid=1;e->reader_before=edmac_get_state(10);
        e->reader_address=(unsigned)edmac_get_address(10);e->reader_pointer=(unsigned)edmac_get_pointer(10);
        e->reader_flags=edmac_get_flags(10);mirror_camera_dma(10,&e->reader);e->reader_after=edmac_get_state(10);
    }
    fx_state state;e->delivered=fx_delivered_state(&state);
    if(e->delivered){e->params=state.params;e->preview_ms=state.last_ms;}
    trace.r.last_event_ms=e->ms;if(pc==NATIVE.trace_start_pc)trace.r.starts++;
    unsigned elapsed=get_us_clock()-began;if(elapsed>trace.r.max_hook_us)trace.r.max_hook_us=elapsed;
    unlock(s);
#else
    (void)regs;(void)stack;
#endif
}
static int install(void)
{
    if(!POINTS||POINTS>MIRROR_NATIVE_POINTS)return MT_GUARD;
    /* Preflight the capture hook too, before leaving even observer hooks in
     * a firmware whose native capture contract does not match this backend. */
    if(!trace.installed)for(unsigned j=0;j<4;j++)
        if(read_value((uint8_t*)(uintptr_t)(NATIVE.stage_pc+j*4),1)!=NATIVE.stage_words[j]){
            trace.r.error_pc=NATIVE.stage_pc+j*4;return MT_GUARD;
        }
    /* Pinned cache_hacks.c uses one locked way and index mask 0x7E0.
     * Reject an internally impossible plan before leaving partial hooks. The
     * core registry still handles collisions with other/core patches. */
    for(unsigned i=0;i<POINTS;i++)for(unsigned j=0;j<i;j++)
        if((points[i].pc&0x7e0u)==(points[j].pc&0x7e0u)&&
           (points[i].pc&~31u)!=(points[j].pc&~31u)){
            trace.r.core_error=0x10;trace.r.error_pc=points[i].pc;return MT_PATCH;
        }
    for(unsigned i=0;i<POINTS;i++)if((points[i].pc&0x7e0u)==(NATIVE.stage_pc&0x7e0u)&&
        (points[i].pc&~31u)!=(NATIVE.stage_pc&~31u)){
        trace.r.core_error=0x10;trace.r.error_pc=points[i].pc;return MT_PATCH;
    }
    for(unsigned i=0;i<POINTS;i++)if(!(trace.installed&(1u<<i))){
        for(unsigned j=0;j<4;j++)if(read_value((uint8_t*)(uintptr_t)(points[i].pc+j*4),1)!=points[i].words[j]){
            trace.r.error_pc=points[i].pc+j*4;return MT_GUARD;
        }
    }
    for(unsigned i=0;i<POINTS;i++)if(!(trace.installed&(1u<<i))){
        if(trace.closed||ml_shutdown_requested)return MT_SHUTDOWN;
        if(trace.r.phase!=MT_QUEUED)return MT_CANCEL;
        int result=patch_hook_function(points[i].pc,points[i].words[0],observe,"Mirror: RAW metadata trace (restart removes)");
        if(result){trace.r.core_error=(unsigned)result;trace.r.error_pc=points[i].pc;return MT_PATCH;}
        trace.installed|=1u<<i;
    }
    return MT_OK;
}
#ifndef MIRROR_RELEASE
static int text(FILE*f,const char*p){if(trace.closed||ml_shutdown_requested)return 0;size_t n=strlen(p);return FIO_WriteFile(f,p,n)==(int)n;}
static void log_write(void)
{
    char path[64],line[512];unsigned n;uint32_t bytes;
    if(!is_dir("ML/LOGS")&&FIO_CreateDirectory("ML/LOGS"))goto fail;
    for(n=0;n<1000;n++){if(trace.closed||ml_shutdown_requested)return;gl_snprintf(path,sizeof(path),"ML/LOGS/MTR%03u.LOG",n);if(FIO_GetFileSize(path,&bytes))break;}
    if(n==1000)goto fail;
    FILE*f=FIO_CreateFile(path);if(!f)goto fail;
    int ok=text(f,"Mirror native CR2 path metadata v2 / EOSM202 / ML ed3e7c0\nRead-only sensor/arguments; runtime cache hooks remain until power OFF\nNo owned RAW lease; no mirrored CR2 saved; sensor/output pointers never dereferenced\n");
    mirror_raw_trace_report*r=&trace.r;
    gl_snprintf(line,sizeof(line),"phase=%u error=%u core_error=%x error_pc=%x installed=%x events=%u dropped=%u skipped=%u max_hook_us=%u requested_ms=%u armed_ms=%u last_ms=%u starts=%u\n",r->phase,r->error,r->core_error,r->error_pc,trace.installed,r->events,r->dropped,r->skipped,r->max_hook_us,r->requested_ms,r->armed_ms,r->last_event_ms,r->starts);if(ok)ok=text(f,line);
    for(unsigned i=0;ok&&i<r->events;i++){
        const event*e=&trace.events[(r->dropped+i)%SLOTS];
        gl_snprintf(line,sizeof(line),"event=%u ms=%u us=%u kind=%u pc=%x lr=%x task=%x desc=%x source_field=%x effective_source=%x x=%u y=%u precision=%x\n",i,e->ms,e->us,e->kind,e->pc,e->lr,e->task,e->descriptor,e->source_field,e->effective_source,e->x,e->y,e->precision);ok=text(f,line);
        gl_snprintf(line,sizeof(line),"rd_channel=%u rd_flags=%x rd_offset=%x wr_channel=%u output_suite=%x output2=%x gui=%u lv=%u job=%u context_job=%x opaque_context=%x\n",e->rd_channel,e->rd_flags,e->rd_offset,e->wr_channel,e->output_suite,e->output2,e->gui,e->lv,e->job,e->context_job,e->opaque_context);if(ok)ok=text(f,line);
        gl_snprintf(line,sizeof(line),"dma_before=%u after=%u address=%x pointer=%x flags=%x xa=%u ya=%u xb=%u yb=%u xn=%u yn=%u off1a=%x off2a=%x off1b=%x off2b=%x off3=%x\n",e->dma_before,e->dma_after,e->dma_address,e->dma_pointer,e->dma_flags,e->xa,e->ya,e->xb,e->yb,e->xn,e->yn,e->off1a,e->off2a,e->off1b,e->off2b,e->off3);if(ok)ok=text(f,line);
        gl_snprintf(line,sizeof(line),"delivered=%u preview_ms=%u params=%u,%u,%u,%u\n",e->delivered,e->preview_ms,e->params.value[0],e->params.value[1],e->params.value[2],e->params.value[3]);if(ok)ok=text(f,line);
        gl_snprintf(line,sizeof(line),"original_cpsr=%x argument_job=%x argument_source=%x reader_valid=%u reader_before=%u reader_after=%u reader_address=%x reader_pointer=%x reader_flags=%x\n",e->original_cpsr,e->argument_job,e->argument_source,e->reader_valid,e->reader_before,e->reader_after,e->reader_address,e->reader_pointer,e->reader_flags);if(ok)ok=text(f,line);
        const mirror_dma_info*q=&e->reader;
        gl_snprintf(line,sizeof(line),"reader_xa=%u reader_ya=%u reader_xb=%u reader_yb=%u reader_xn=%u reader_yn=%u reader_off1a=%x reader_off2a=%x reader_off1b=%x reader_off2b=%x reader_off3=%x\n",q->xa,q->ya,q->xb,q->yb,q->xn,q->yn,q->off1a,q->off2a,q->off1b,q->off2b,q->off3);if(ok)ok=text(f,line);
    }
    FIO_CloseFile(f);if(!ok)goto fail;
    gl_snprintf(trace.r.log,sizeof(trace.r.log),"%s",path);return;
fail:
    if(!trace.closed&&!ml_shutdown_requested){trace.r.phase=MT_FAILED;trace.r.error=MT_LOG;}
}
#endif
void mirror_raw_trace_service(void)
{
    if(!mirror_camera_native())return;
    if(ml_shutdown_requested||trace.closed){mirror_raw_trace_shutdown();return;}
    unsigned now=get_ms_clock();
    if(trace.r.phase==MT_QUEUED){
        fx_state state;
        if(!fx_delivered_state(&state)){if(!trace.runtime)end(MT_NO_PREVIEW);}
        else if(!trace.runtime&&now-trace.r.requested_ms>15000)end(MT_TIMEOUT);
        else if(!gui_menu_shown()&&!lens_info.job_state&&!get_halfshutter_pressed()&&lv&&!lv_paused&&
                gui_state!=1&&gui_state!=3&&gui_state!=12){
            int error=install();if(error)end((unsigned)error);
            else{unsigned s=lock();if(!trace.closed&&trace.r.phase==MT_QUEUED&&!lens_info.job_state&&!get_halfshutter_pressed()){
                trace.r.phase=MT_ARMED;trace.r.armed_ms=get_ms_clock();trace.active=!trace.runtime;}unlock(s);}
        }
    }
    if(ml_shutdown_requested||trace.closed){mirror_raw_trace_shutdown();return;}
    unsigned s=lock();now=get_ms_clock();
    if(trace.r.phase==MT_ARMED&&!trace.runtime){
        if(now-trace.r.armed_ms>60000)end_locked(trace.r.starts?MT_OK:MT_TIMEOUT);
        else if(trace.r.starts&&now-trace.r.last_event_ms>=750&&!lens_info.job_state)end_locked(MT_OK);
    }
    unlock(s);
#ifndef MIRROR_RELEASE
    if(trace.log_pending&&!lens_info.job_state){
        unsigned s=lock();trace.log_pending=0;trace.writing=1;unlock(s);
        log_write();s=lock();trace.writing=0;unlock(s);
    }
#endif
}
