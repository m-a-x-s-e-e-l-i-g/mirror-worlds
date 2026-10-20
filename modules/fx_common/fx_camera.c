/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade).
 * ML display/keys, config lookup and allocator ABI: pinned ML contributors.
 * Shared source is privately namespaced into each independently loaded module.
 * Effect descriptors supply controls, preparation, pixels and provenance. No RAW/exposure/shutter injection. */
#ifdef FX_HOST_TEST
#include "fx_sdk.h"
#else
#include <module.h>
#include <dryos.h>
#include <menu.h>
#include <property.h>
#include <lens.h>
#include <vram.h>
#include <arm-mcr.h>
#include <config.h>
#endif
#include <string.h>
#include "fx_camera.h"
#include "gl_format.h"
#include "gl_memory_ml.h"
#include "fx_copy.h"
#ifdef FX_PRIVATE_CPU_HEAP
#include "fx_memory_plan.h"
/* Pinned src/mem.c exports direct wrappers, bypassing automatic photo/SRM
 * fallback. These three buffers are only CPU-accessed; none is an EDMAC/FIO
 * destination. Pair each raw pointer with the SAME backend's free. */
extern int GetFreeMemForMalloc(void);
extern void *__priv_malloc(size_t size);
extern void __priv_free(void *memory);
#endif
/* Exact pinned-core APIs. Disable clears transient Magic Zoom triggers, not
 * the user's saved setting; core handles zoom events before module keys. */
extern void zoom_overlay_disable(void);
extern int should_draw_zoom_overlay(void);
extern int zebra_should_run(void);
#define W 720u
#define H 480u
#define PITCH 1440u
#define BYTES (PITCH*H)
#define FX_STRING_(s) #s
#define FX_STRING(s) FX_STRING_(s)
enum { CAP_NONE, CAP_PENDING, CAP_READY, CAP_WRITING, CAP_DONE, CAP_FAILED, CAP_COPYING };
enum { ERR_MEMORY=10, ERR_CONFLICT, ERR_LAYOUT, ERR_PIXELS, ERR_WAIT, ERR_FILE, ERR_CANCEL };
static struct {
    fx_status report;
    fx_state engine[2], captured;
    uint32_t times[2][720], captured_times[720];
    fx_params desired, held;
    void *raw[3]; unsigned char *image[3]; /* 0 committed canvas; 2 retained snapshot. */
    size_t scratch_bytes,canvas_bytes;
    unsigned scratch_generation;
    int scratch_held,canvas_valid,tearing_down;
    void *workspace_raw,*workspace;size_t workspace_size;int work_writing;
    gl_review review;
    int current, painting, initialized, requested, reset, log_requested;
    volatile int stop;
    unsigned delivered_ms, queued_ms, duration, set_release, arrow_release;
    unsigned canon_controls,canon_gui;
} camera;
static unsigned lock(void){unsigned irq=cli();__asm__ __volatile__("" ::: "memory");return irq;}
static void unlock(unsigned irq){__asm__ __volatile__("" ::: "memory");sei(irq);}
static int native_review(void){return camera.canon_controls&&(camera.canon_gui==1||camera.canon_gui==3||camera.canon_gui==12);}
static void copy_pixels(void*dest,const void*src)
{
    fx_copy_cpu(dest,src,BYTES);
}
void fx_canon_gui(unsigned state)
{
    unsigned irq=lock();camera.canon_controls=1;camera.canon_gui=state;
    if(native_review())gl_review_key(&camera.review,GL_R_DISMISS,get_ms_clock());
    unlock(irq);
}
static int layout(void){return lv&&!lv_paused&&lv_dispsize==1&&!ext_monitor_hdmi&&!sensor_cleaning&&
    !ml_shutdown_requested&&vram_lv.width==720&&vram_lv.height==480&&vram_lv.pitch==1440;}
static int family(const char *n){return !strcmp(n,"glock")||!strcmp(n,"slitscan")||!strcmp(n,"mirror")||
    !strcmp(n,"feedback")||!strcmp(n,"fragment")||!strcmp(n,"diffract");}
static int claim(void)
{
    /* Resolve outside the IRQ lock; loaded module/config tables are core-owned.
     * Unknown older family modules are refused, even when their menu is closed. */
    const int *busy[6];unsigned count=0;
    for(int id=module_get_next_loaded(-1);id>=0;id=module_get_next_loaded(id)){
        const char*n=module_get_name(id);
        if(n&&family(n)&&strcmp(n,FX_STRING(FX_PREFIX))){
            char name[64];gl_snprintf(name,sizeof(name),"maxmade.fx.%s.busy",n);
            struct config_var*v=module_get_config_var(name);
            if(!v||!v->value||count>=6)return 0;
            busy[count++]=v->value;
        }
    }
    unsigned irq=lock();
    for(unsigned i=0;i<count;i++)if(*busy[i]){unlock(irq);return 0;}
    FX(active)=1;unlock(irq);return 1;
}
void fx_camera_init(void)
{
    memset(&camera,0,sizeof(camera));camera.desired=FX(effect).defaults;
    gl_review_init(&camera.review);camera.duration=3000;FX(active)=0;
}
int fx_native_capture_mode(void)
{
    unsigned irq=lock();
    int valid=!FX(active)&&!camera.initialized&&!camera.painting&&!camera.report.allocated&&
        !camera.review.have_image&&!FX(effect).temporal;
    if(valid)camera.report.native_capture=1;
    unlock(irq);return valid;
}
int fx_private_cpu_heap_mode(void)
{
#ifdef FX_PRIVATE_CPU_HEAP
    unsigned irq=lock();
    int valid=!FX(active)&&!camera.initialized&&!camera.painting&&!camera.work_writing&&
        !camera.report.allocated&&!camera.report.native_capture&&!camera.scratch_held&&
        (FX(effect).temporal==2||FX(effect).temporal==3);
    if(valid)camera.report.cpu_memory=1;
    unlock(irq);return valid;
#else
    return 0;
#endif
}
static void *private_alloc(unsigned block,size_t bytes)
{
#ifdef FX_PRIVATE_CPU_HEAP
    if(camera.report.cpu_memory&&(camera.report.cpu_mask&(1u<<block))){
        int free_now=GetFreeMemForMalloc();
        if(!bytes||bytes>4u*1024u*1024u||free_now<0||(size_t)free_now<bytes+FX_CPU_RESERVE)return 0;
        return __priv_malloc(bytes);
    }
#else
    (void)block;
#endif
    return gl_display_alloc(bytes);
}
static void private_free(unsigned block,void*raw)
{
#ifdef FX_PRIVATE_CPU_HEAP
    if(camera.report.cpu_memory&&(camera.report.cpu_mask&(1u<<block))){__priv_free(raw);return;}
#else
    (void)block;
#endif
    gl_display_free(raw);
}
static int private_reserves(void)
{
#ifdef FX_PRIVATE_CPU_HEAP
    if(camera.report.cpu_memory){
        int dma=GetFreeMemForAllocateMemory(),cpu=GetFreeMemForMalloc();
        camera.report.private_dma_after=dma<0?0:(unsigned)dma;
        camera.report.private_cpu_after=cpu<0?0:(unsigned)cpu;
        /* Pools may alias or race with Canon allocation. Never assume that a
         * successful per-pool plan makes their summed free space independent. */
        return dma>=0&&(unsigned)dma>=FX_DMA_RESERVE&&
            (!camera.report.cpu_mask||(cpu>=0&&(unsigned)cpu>=FX_CPU_RESERVE));
    }
#endif
    return 1;
}
int fx_capture_scratch_configure(size_t bytes)
{
    unsigned irq=lock();
    int valid=camera.report.native_capture&&!FX(effect).temporal&&!FX(active)&&
        !camera.initialized&&!camera.painting&&!camera.work_writing&&
        !camera.scratch_held&&!camera.report.allocated&&bytes<=4u*1024u*1024u;
    if(valid)camera.scratch_bytes=bytes;
    unlock(irq);return valid;
}
int fx_capture_scratch_acquire(fx_capture_scratch*out)
{
    if(!out)return 0;
    unsigned irq=lock();
    int valid=camera.report.native_capture&&camera.scratch_bytes&&FX(active)&&
        camera.initialized&&camera.report.running&&!camera.stop&&!ml_shutdown_requested&&
        !camera.painting&&!camera.work_writing&&!camera.scratch_held&&!camera.tearing_down&&
        camera.canvas_valid&&!camera.review.state&&!native_review()&&camera.image[0];
    if(valid){
        camera.scratch_held=1;camera.canvas_valid=0;
        if(!++camera.scratch_generation)++camera.scratch_generation;
        *out=(fx_capture_scratch){camera.image[0],camera.canvas_bytes,camera.scratch_generation};
    }
    unlock(irq);return valid;
}
int fx_capture_scratch_release(const fx_capture_scratch*lease)
{
    if(!lease)return 0;
    unsigned irq=lock();
    int valid=camera.scratch_held&&lease->data==camera.image[0]&&
        lease->size==camera.canvas_bytes&&lease->generation==camera.scratch_generation;
    if(valid)camera.scratch_held=0;
    /* The old canvas remains invalid until a fresh accepted render commits.
     * Never expose bitmap bytes through half-edge rollback or error fallback. */
    unlock(irq);return valid;
}
int fx_start(void)
{
    if(FX(active))return 0;
    if(!claim()){camera.report.error=ERR_CONFLICT;return 0;}
    camera.stop=0;camera.requested=1;return 1;
}
void fx_stop(void){camera.stop=1;}
void fx_reset(void){unsigned irq=lock();if(camera.report.running)camera.reset=1;unlock(irq);}
int fx_controls(const fx_params*p)
{
    if(!FX(effect).validate(p))return 0;
    unsigned irq=lock();camera.desired=*p;unlock(irq);return 1;
}
int fx_configure(const fx_slit_params*p)
{
    if(!p)return 0;
    fx_params generic={{p->direction,p->speed,p->width}};
    return fx_controls(&generic);
}
void fx_half(int down)
{
    unsigned irq=lock();down=down!=0;
    gl_review_half(&camera.review,down);
    if(camera.report.half!=(unsigned)down){
        camera.report.half=down;
        camera.report.frozen=down&&camera.canvas_valid&&camera.engine[camera.current].initialized;
        if(camera.report.frozen)camera.held=camera.engine[camera.current].params;
    }
    unlock(irq);
}
int fx_capture(void)
{
    unsigned irq=lock();
    if(camera.report.native_capture||!camera.report.running||camera.stop||!camera.engine[camera.current].initialized||
       camera.review.state||native_review()||(camera.report.capture>=CAP_PENDING&&camera.report.capture<=CAP_WRITING)||
       camera.report.capture==CAP_COPYING){unlock(irq);return 0;}
    camera.report.capture=CAP_PENDING;camera.report.capture_error=0;
    camera.report.request_ms=camera.queued_ms=get_ms_clock();
    camera.review.have_image=0;camera.review.revision++;
    camera.report.path[0]=0;
    unlock(irq);return 1;
}
int fx_key(unsigned key)
{
    unsigned irq=lock();
    if(key==MODULE_KEY_UNPRESS_SET&&camera.set_release){camera.set_release=0;unlock(irq);return 0;}
    if(key==MODULE_KEY_UNPRESS_UDLR&&camera.arrow_release){camera.arrow_release=0;unlock(irq);return 0;}
    int active=FX(active)&&camera.report.running&&!camera.stop;
    if(camera.canon_controls&&(native_review()||key==MODULE_KEY_PLAY)){
        if(key==MODULE_KEY_PLAY)gl_review_key(&camera.review,GL_R_DISMISS,get_ms_clock());
        unlock(irq);return 1;
    }
    /* Mirror's normal camera controls include SET. Its user capture workflow
     * is the physical shutter; do not turn SET into a TIFF export. */
    if(camera.canon_controls&&key==MODULE_KEY_PRESS_SET&&!camera.review.state){unlock(irq);return 1;}
    if(active&&key==MODULE_KEY_PRESS_HALFSHUTTER){
        camera.report.zoom_resets++;unlock(irq);
        zoom_overlay_disable();fx_half(1);return 1; /* Preserve Canon AF/shutter handling. */
    }
    unsigned mapped=999;
    if(key==MODULE_KEY_PLAY)mapped=GL_R_PLAY;
    else if(key==MODULE_KEY_WHEEL_RIGHT)mapped=GL_R_ZOOM_IN;
    else if(key==MODULE_KEY_WHEEL_LEFT)mapped=GL_R_ZOOM_OUT;
    else if(key==MODULE_KEY_PRESS_LEFT)mapped=GL_R_LEFT;
    else if(key==MODULE_KEY_PRESS_RIGHT)mapped=GL_R_RIGHT;
    else if(key==MODULE_KEY_PRESS_UP)mapped=GL_R_UP;
    else if(key==MODULE_KEY_PRESS_DOWN)mapped=GL_R_DOWN;
    else if(key==MODULE_KEY_PRESS_SET||key==MODULE_KEY_MENU)mapped=GL_R_DISMISS;
    int handled=active&&mapped!=999&&gl_review_key(&camera.review,mapped,get_ms_clock())==GL_OK;
    if(handled&&key==MODULE_KEY_PRESS_SET)camera.set_release=1;
    if(handled&&mapped>=GL_R_LEFT&&mapped<=GL_R_DOWN)camera.arrow_release=1;
    unlock(irq);
    if(key==MODULE_KEY_MENU)return 1; /* Dismiss but pass menu opening to Canon/ML. */
    if(handled)return 0;
    if(active&&!gui_menu_shown()&&key==MODULE_KEY_PRESS_SET){
        irq=lock();camera.set_release=1;unlock(irq);fx_capture();return 0;
    }
    /* Shutter and ordinary unhandled controls always pass through. */
    return 1;
}
void fx_review_time(unsigned ms){unsigned irq=lock();gl_review_duration(&camera.review,ms);camera.duration=camera.review.configured_ms;unlock(irq);}
void fx_status_get(fx_status*out){if(!out)return;unsigned irq=lock();*out=camera.report;
    out->review_state=camera.review.state;out->review_zoom=camera.review.zoom;unlock(irq);}
void fx_diagnostics(void){camera.log_requested=1;}
int fx_delivered_state(fx_state*out)
{
    if(!out)return 0;
    unsigned irq=lock();int valid=camera.report.running&&!camera.stop&&camera.canvas_valid&&camera.engine[camera.current].initialized;
    if(valid)*out=camera.engine[camera.current];
    unlock(irq);return valid;
}
static void copy_snapshot(void)
{
    /* Called only by the display task, with painting held. The previous
     * committed canvas cannot change until this callback commits its candidate. */
    unsigned irq=lock();camera.report.capture=CAP_COPYING;
    unsigned old=camera.current;camera.captured=camera.engine[old];unlock(irq);
    memcpy(camera.image[2],camera.image[0],BYTES);
    memcpy(camera.captured_times,camera.times[old],sizeof(camera.captured_times));
    sync_caches();
    irq=lock();camera.report.snapshot_ms=get_ms_clock();
    camera.report.capture=camera.stop?CAP_FAILED:CAP_READY;
    if(camera.stop)camera.report.capture_error=ERR_CANCEL;
    unlock(irq);
}
unsigned int fx_filter(void *context)
{
    unsigned irq=lock();
    if(camera.scratch_held){unlock(irq);return 0;}
    int ready=camera.report.running&&!camera.stop&&layout()&&!gui_menu_shown()&&!native_review();
    if(!context){unlock(irq);return ready;}
    if(native_review()){unlock(irq);return 0;} /* Never paint over Canon review. */
    /* The core can retain a positive query across a mode/geometry change.
     * Its buffer API carries no capacity, so never assume our native byte
     * count after that geometry has ceased to hold. */
    if(!layout()){unlock(irq);return 0;}
    struct display_filter_buffers*b=context;
    if(!b->src_buf||!b->dst_buf||b->src_buf==b->dst_buf||camera.painting){unlock(irq);return 0;}
    if(!ready){unlock(irq);memcpy(b->dst_buf,b->src_buf,BYTES);sync_caches();return 0;}
    camera.painting=1;unsigned old=camera.current,next=1-old;
    unsigned started=get_ms_clock();
    gl_review review=camera.review;
    if(review.state){
        /* Scale the immutable retained image into the core-owned destination.
         * No persistent zoom canvas is needed; temporal history stays intact. */
        unlock(irq);
        int result;
        if(review.zoom==1){memcpy(b->dst_buf,camera.image[2],BYTES);result=GL_OK;}
        else result=gl_review_scale(camera.image[2],BYTES,b->dst_buf,BYTES,W,H,PITCH,
            review.zoom,review.center_x,review.center_y,&camera.stop);
        sync_caches();irq=lock();
        int valid=result==GL_OK&&!camera.stop&&layout()&&!gui_menu_shown()&&
            camera.review.state&&camera.review.revision==review.revision;
        if(valid)gl_review_delivered(&camera.review,review.revision,get_ms_clock());
        else{
            int compose=!camera.stop&&layout()&&!gui_menu_shown();unlock(irq);
            memcpy(b->dst_buf,compose?camera.image[0]:b->src_buf,BYTES);sync_caches();irq=lock();
        }
        camera.painting=0;unlock(irq);return 0;
    }
    fx_params p=camera.report.frozen?camera.held:camera.desired;
    fx_state previous=camera.engine[old];
    int resetting=camera.reset;
    if(resetting||!camera.canvas_valid)previous.initialized=0;
    int prepared=!camera.work_writing&&FX(effect).ready(camera.workspace,camera.workspace_size,&p,W,H,PITCH);
    unlock(irq);
    /* The core owns a separate output buffer for this synchronous callback.
     * Keep the previous committed pixels untouched until delivery is accepted. */
    int error=prepared?FX(effect).render(&previous,&camera.engine[next],b->src_buf,camera.image[0],b->dst_buf,
        BYTES,W,H,PITCH,camera.times[old],camera.times[next],&p,started,camera.workspace,camera.workspace_size):4;
    unsigned rendered=get_ms_clock();
    if(error)memcpy(b->dst_buf,b->src_buf,BYTES);
    sync_caches();irq=lock();
    camera.report.kernel_ms=rendered-started;camera.report.display_ms=get_ms_clock()-rendered;
    if(camera.report.capture==CAP_PENDING){unlock(irq);copy_snapshot();irq=lock();}
    int valid=!error&&!camera.stop&&!camera.review.state&&!native_review()&&layout()&&!gui_menu_shown()&&
        (!camera.report.frozen||!memcmp(&p,&camera.held,sizeof(p)));
    if(valid){
        if(resetting)camera.reset=0;
        camera.current=next;camera.canvas_valid=1;camera.report.frames++;
        unsigned now=get_ms_clock();camera.report.interval_ms=camera.delivered_ms?now-camera.delivered_ms:0;
        if(camera.report.interval_ms>camera.report.max_interval_ms)camera.report.max_interval_ms=camera.report.interval_ms;
        camera.delivered_ms=now;camera.report.gaps=camera.engine[next].gaps;
        if(camera.report.half&&!camera.report.frozen){camera.held=p;camera.report.frozen=1;}
        /* Publish controls before refreshing the committed canvas: half/capture
         * edges during this copy now refer to the accepted display. Painting
         * excludes another filter, geometry preparation and teardown throughout. */
        unsigned copying=get_ms_clock();unlock(irq);copy_pixels(camera.image[0],b->dst_buf);
        /* This private canvas is read only by CPU code, never Canon DMA.
         * Avoid a second full D/I cache sync and cache-patch reapplication. */
#ifdef FX_HOST_TEST
        fx_test_committed_canvas();
#endif
        irq=lock();camera.report.commit_ms=get_ms_clock()-copying;
    }else{
        camera.report.discarded++;if(error&&error!=4)camera.report.error=ERR_PIXELS;
        int have=camera.canvas_valid&&camera.engine[old].initialized;unlock(irq);
        memcpy(b->dst_buf,have?camera.image[0]:b->src_buf,BYTES);sync_caches();irq=lock();
    }
    camera.report.render_ms=get_ms_clock()-started;camera.painting=0;unlock(irq);return 0;
}
static int write_data(void*context,const void*data,size_t size)
{return FIO_WriteFile(context,data,size)==(int)size;}
static int text(FILE*f,const char*s){return write_data(f,s,strlen(s));}
static int exists(const char*p){uint32_t size;return FIO_GetFileSize(p,&size)==0;}
static int save(void)
{
    char tif[64],json[64],ok[64],line[512];unsigned number;
    if(!is_dir("ML/GLITCH")&&FIO_CreateDirectory("ML/GLITCH")!=0)return ERR_FILE;
    for(number=0;number<10000;number++){
        gl_snprintf(tif,sizeof(tif),"ML/GLITCH/%s%04u.TIF",FX(effect).prefix,number);
        gl_snprintf(json,sizeof(json),"ML/GLITCH/%s%04u.JSN",FX(effect).prefix,number);
        gl_snprintf(ok,sizeof(ok),"ML/GLITCH/%s%04u.OK",FX(effect).prefix,number);
        if(!exists(tif)&&!exists(json)&&!exists(ok))break;
    }
    if(number==10000)return ERR_FILE;
    FILE*f=FIO_CreateFile(tif);if(!f)return ERR_FILE;
    unsigned char row[W*3];
    int error=fx_tiff_write_ex(camera.image[2],BYTES,W,H,PITCH,row,sizeof(row),write_data,f,&camera.stop,FX(effect).description);
    FIO_CloseFile(f);uint32_t size=0;
    if(error||FIO_GetFileSize(tif,&size)||size!=512+W*H*3){FIO_RemoveFile(tif);return camera.stop?ERR_CANCEL:ERR_FILE;}
    f=FIO_CreateFile(json);if(!f)return ERR_FILE;
    fx_state*s=&camera.captured;
    gl_snprintf(line,sizeof(line),"{\"kind\":\"%s\",\"module\":\"%s\",\"version\":\"%s\",\"width\":720,\"height\":480,\"request_ms\":%u,\"last_frame_ms\":%u,",
        FX(effect).kind,FX(effect).module,FX(effect).version,camera.report.request_ms,s->last_ms);
    int valid=text(f,line);unsigned json_bytes=(unsigned)strlen(line);
    for(unsigned i=0;valid&&i<FX(effect).param_count;i++){
        gl_snprintf(line,sizeof(line),"\"%s\":%u,",FX(effect).param_names[i],s->params.value[i]);
        valid=text(f,line);json_bytes+=(unsigned)strlen(line);
    }
    if(valid&&FX(effect).metadata){
        int count=FX(effect).metadata(s,line,sizeof(line));
        if(count<0||(unsigned)count>=sizeof(line))valid=0;
        else {valid=write_data(f,line,(unsigned)count);json_bytes+=(unsigned)count;}
    }
    if(FX(effect).temporal==1||FX(effect).temporal==3){
        gl_snprintf(line,sizeof(line),"\"%s\":[",FX(effect).temporal==3?"tile_ms":"slice_ms");
        if(valid)valid=text(f,line);
        json_bytes+=(unsigned)strlen(line);
        unsigned axis=FX(effect).time_count(&s->params,W,H);
        for(unsigned i=0;valid&&i<axis;i++){
            if(camera.stop){valid=0;break;}
            gl_snprintf(line,sizeof(line),"%s%u",i?",":"",camera.captured_times[i]);
            valid=text(f,line);json_bytes+=(unsigned)strlen(line);
        }
        if(valid){valid=text(f,"]}\n");json_bytes+=3;}
    }else{
        gl_snprintf(line,sizeof(line),"\"source_ms\":%u}\n",s->last_ms);
        if(valid)valid=text(f,line);
        json_bytes+=(unsigned)strlen(line);
    }
    FIO_CloseFile(f);
    if(FIO_GetFileSize(json,&size)||size!=json_bytes)valid=0;
    if(!valid){FIO_RemoveFile(json);return camera.stop?ERR_CANCEL:ERR_FILE;}
    if(camera.stop)return ERR_CANCEL;
    f=FIO_CreateFile(ok);if(!f)return ERR_FILE;
    const char marker[]="MAXmade effect complete: rendered 720x480 TIFF plus provenance\n";
    valid=text(f,marker);FIO_CloseFile(f);
    if(!valid||FIO_GetFileSize(ok,&size)||size!=sizeof(marker)-1){FIO_RemoveFile(ok);return ERR_FILE;}
    gl_snprintf(camera.report.path,sizeof(camera.report.path),"%s",tif);return 0;
}
static void diagnostics(void)
{
    camera.log_requested=0;
#ifndef MIRROR_RELEASE
    if(!is_dir("ML/LOGS")&&FIO_CreateDirectory("ML/LOGS")!=0)return;
    char path[64],line[256];unsigned n;
    for(n=0;n<1000;n++){gl_snprintf(path,sizeof(path),"ML/LOGS/%s%03u.LOG",FX(effect).log_prefix,n);if(!exists(path))break;}
    if(n==1000)return;
    FILE*f=FIO_CreateFile(path);if(!f)return;
    fx_status r;fx_status_get(&r);
    gl_snprintf(line,sizeof(line),"%s %s / EOSM202 / ML ed3e7c0\n%s\n",FX(effect).title,FX(effect).version,
        r.native_capture?"Native Canon capture backend; private LCD preview":"Rendered 720x480; no RAW/full-shutter binding");
    int valid=text(f,line);
    gl_snprintf(line,sizeof(line),"running=%u frames=%u discarded=%u half=%u frozen=%u error=%u render_ms=%u interval_ms=%u allocated=%u peak=%u gaps=%u\n",
        r.running,r.frames,r.discarded,r.half,r.frozen,r.error,r.render_ms,r.interval_ms,r.allocated,r.peak,r.gaps);
    if(valid)valid=text(f,line);
    gl_snprintf(line,sizeof(line),"capture=%u error=%u saved=%u request_ms=%u snapshot_ms=%u review=%u zoom=%u file=%s\n",
        r.capture,r.capture_error,r.saved,r.request_ms,r.snapshot_ms,r.review_state,r.review_zoom,r.path);
    if(valid)valid=text(f,line);
    gl_snprintf(line,sizeof(line),"preparing=%u prepare_ms=%u\n",r.preparing,r.prepare_ms);
    if(valid)valid=text(f,line);
    gl_snprintf(line,sizeof(line),"free_initial=%u free_failed=%u required_with_reserve=%u reserve=%u allocation_stage=%u\n",
        r.free_initial,r.free_failed,r.required,r.reserve,r.allocation_stage);
    if(valid)valid=text(f,line);
    gl_snprintf(line,sizeof(line),"kernel_ms=%u display_sync_ms=%u commit_copy_ms=%u max_interval_ms=%u zoom_trigger_resets=%u core_ready=%u zoom_active=%u\n",
        r.kernel_ms,r.display_ms,r.commit_ms,r.max_interval_ms,r.zoom_resets,r.core_ready,r.zoom_active);
    if(valid)valid=text(f,line);
    gl_snprintf(line,sizeof(line),"native_capture_policy=%u\n",r.native_capture);
    if(valid)valid=text(f,line);
#ifdef FX_PRIVATE_CPU_HEAP
    if(r.cpu_memory){
        gl_snprintf(line,sizeof(line),"private_cpu_heap=1 cpu_mask=%u cpu_initial=%u cpu_failed=%u dma_required=%u cpu_required=%u cpu_reserve=%u\n",
            r.cpu_mask,r.cpu_initial,r.cpu_failed,r.dma_required,r.cpu_required,r.cpu_reserve);
        if(valid)valid=text(f,line);
        gl_snprintf(line,sizeof(line),"private_dma_after=%u private_cpu_after=%u\n",r.private_dma_after,r.private_cpu_after);
        if(valid)valid=text(f,line);
    }
#endif
    FIO_CloseFile(f);
    if(valid)gl_snprintf(camera.report.log,sizeof(camera.report.log),"%s",path);
#endif
}
void fx_service(void)
{
    if(ml_shutdown_requested)camera.stop=1;
    if(camera.requested){
        camera.requested=0;camera.report.error=0;
        if(camera.stop)goto cleanup;
        if(module_display_filter_enabled()){camera.report.error=ERR_CONFLICT;camera.stop=1;goto cleanup;}
        int available=GetFreeMemForAllocateMemory();
        camera.report.free_initial=available<0?0:(unsigned)available;camera.report.free_failed=0;
        camera.report.reserve=1536u*1024u;camera.report.allocation_stage=1;
        unsigned images=camera.report.native_capture?1:2;
        camera.canvas_bytes=camera.scratch_bytes>BYTES?camera.scratch_bytes:BYTES;
        camera.report.required=(unsigned)camera.canvas_bytes+(images-1)*BYTES+
            (unsigned)FX(effect).workspace_size+camera.report.reserve;
        int enough=available>=0&&(unsigned)available>=camera.report.required;
#ifdef FX_PRIVATE_CPU_HEAP
        if(camera.report.cpu_memory){
            int cpu=GetFreeMemForMalloc();fx_memory_plan plan;
            size_t bytes[3]={camera.canvas_bytes,(images-1)*BYTES,FX(effect).workspace_size};
            camera.report.cpu_initial=cpu<0?0:(unsigned)cpu;camera.report.cpu_failed=0;
            camera.report.private_dma_after=camera.report.private_cpu_after=0;
            camera.report.cpu_reserve=FX_CPU_RESERVE;camera.report.cpu_mask=0;
            camera.report.cpu_required=0;camera.report.dma_required=camera.report.required;
            enough=fx_memory_choose(bytes,available,cpu,&plan);
            if(enough){camera.report.cpu_mask=plan.cpu_mask;camera.report.cpu_required=plan.cpu_required;camera.report.dma_required=plan.dma_required;}
        }
#endif
        if(!enough){
            camera.report.error=ERR_MEMORY;camera.stop=1;goto cleanup;
        }
        memset(camera.engine,0,sizeof(camera.engine));camera.current=0;camera.canvas_valid=0;
        camera.report.half=camera.report.frozen=0;
        for(unsigned i=0;i<images;i++){
            unsigned slot=i?2:0;
            camera.report.allocation_stage=2+i;
            size_t bytes=slot?BYTES:camera.canvas_bytes;
            camera.raw[slot]=private_alloc(i,bytes);
            if(!camera.raw[slot]){camera.report.error=ERR_MEMORY;camera.stop=1;goto cleanup;}
            camera.image[slot]=CACHEABLE(camera.raw[slot]);camera.report.allocated+=(unsigned)bytes;
            if(camera.report.allocated>camera.report.peak)camera.report.peak=camera.report.allocated;
            if(camera.stop||ml_shutdown_requested){camera.stop=1;goto cleanup;}
            if(!private_reserves()){camera.report.error=ERR_MEMORY;camera.stop=1;goto cleanup;}
        }
        camera.workspace_size=FX(effect).workspace_size;
        if(camera.workspace_size){
            camera.report.allocation_stage=4;
            camera.workspace_raw=private_alloc(2,camera.workspace_size);
            if(!camera.workspace_raw){camera.report.error=ERR_MEMORY;camera.stop=1;goto cleanup;}
            camera.workspace=CACHEABLE(camera.workspace_raw);camera.report.allocated+=(unsigned)camera.workspace_size;
            if(camera.report.allocated>camera.report.peak)camera.report.peak=camera.report.allocated;
            if(camera.stop||ml_shutdown_requested){camera.stop=1;goto cleanup;}
            if(!private_reserves()){camera.report.error=ERR_MEMORY;camera.stop=1;goto cleanup;}
            memset(camera.workspace,0,camera.workspace_size);
            if(camera.report.allocated>camera.report.peak)camera.report.peak=camera.report.allocated;
        }
        camera.report.allocation_stage=0;
        sync_caches();camera.initialized=1;camera.report.running=1;camera.report.capture=CAP_NONE;
        camera.review.have_image=0;camera.review.state=GL_R_OFF;camera.delivered_ms=0;camera.report.max_interval_ms=0;
    }
    if(FX(active)&&camera.initialized){
        if(should_draw_zoom_overlay()){zoom_overlay_disable();camera.report.zoom_resets++;}
        camera.report.core_ready=zebra_should_run();camera.report.zoom_active=should_draw_zoom_overlay();
        fx_half(get_halfshutter_pressed());get_yuv422_vram();
        unsigned preparing_irq=lock();
        fx_params preparation=camera.report.frozen?camera.held:camera.desired;
        int prepare=!camera.painting&&!camera.work_writing&&!camera.scratch_held&&!camera.stop&&
            !FX(effect).ready(camera.workspace,camera.workspace_size,&preparation,W,H,PITCH);
        if(prepare){camera.work_writing=1;camera.report.preparing=1;}
        unlock(preparing_irq);
        if(prepare){
            unsigned begin=get_ms_clock();
            int result=FX(effect).prepare(camera.workspace,camera.workspace_size,&preparation,W,H,PITCH,&camera.stop);
            sync_caches();preparing_irq=lock();camera.work_writing=0;camera.report.preparing=0;
            camera.report.prepare_ms=get_ms_clock()-begin;
            if(result!=FX_OK&&!camera.stop){camera.report.error=ERR_PIXELS;camera.stop=1;}
            unlock(preparing_irq);
        }
        unsigned irq=lock();gl_review_tick(&camera.review,get_ms_clock());
        int pending=camera.report.capture==CAP_PENDING;
        if(pending&&(unsigned)(get_ms_clock()-camera.queued_ms)>=2000){camera.report.capture=CAP_FAILED;camera.report.capture_error=ERR_WAIT;}
        if(camera.report.capture==CAP_READY&&!camera.stop){camera.report.capture=CAP_WRITING;unlock(irq);
            int error=save();irq=lock();camera.report.capture_error=error;
            camera.report.capture=error?CAP_FAILED:CAP_DONE;
            if(!error){camera.report.saved++;gl_review_publish(&camera.review,camera.report.saved,get_ms_clock());}
            else gl_review_fail(&camera.review,error);
        }
        unlock(irq);
    }
cleanup:
    ;unsigned cleanup_irq=lock();
    int cleanup=camera.stop&&FX(active)&&!camera.painting&&!camera.work_writing&&
        !camera.scratch_held&&!camera.tearing_down&&camera.report.capture!=CAP_WRITING;
    if(cleanup)camera.tearing_down=1;
    unlock(cleanup_irq);
    if(cleanup){
        if(camera.report.frames&&!ml_shutdown_requested)camera.log_requested=1;
        if(camera.report.error==ERR_MEMORY){
            int free_now=GetFreeMemForAllocateMemory();camera.report.free_failed=free_now<0?0:(unsigned)free_now;
#ifdef FX_PRIVATE_CPU_HEAP
            if(camera.report.cpu_memory){int cpu=GetFreeMemForMalloc();camera.report.cpu_failed=cpu<0?0:(unsigned)cpu;}
#endif
            camera.log_requested=1;
        }
        camera.report.running=0;camera.review.state=GL_R_OFF;camera.review.have_image=0;
        if(camera.report.capture==CAP_PENDING||camera.report.capture==CAP_READY){camera.report.capture=CAP_FAILED;camera.report.capture_error=ERR_CANCEL;}
        sync_caches();
        for(unsigned i=0;i<3;i++)if(camera.raw[i]){
            private_free(i?1:0,camera.raw[i]);camera.raw[i]=0;camera.image[i]=0;
            camera.report.allocated-=(unsigned)(i?BYTES:camera.canvas_bytes);
        }
        if(camera.workspace_raw){
            private_free(2,camera.workspace_raw);camera.workspace_raw=0;camera.workspace=0;
            camera.report.allocated-=(unsigned)camera.workspace_size;camera.workspace_size=0;
        }
        cleanup_irq=lock();camera.initialized=0;camera.canvas_valid=0;
        camera.canvas_bytes=0;camera.tearing_down=0;FX(active)=0;unlock(cleanup_irq);
    }
    if(camera.log_requested)diagnostics();
}
