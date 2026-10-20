/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade).
 * Probe the pinned real photo/QR source without faking GUI/LV or taking factory
 * exposures. This establishes evidence only, NOT ownership for a long DNG save. */
#include <string.h>
#ifdef FX_PHOTO_HOST_TEST
#include "capture_sdk.h"
#include "raw.h"
#else
#include <module.h>
#include <dryos.h>
#include <property.h>
#include <lens.h>
#include <shoot.h>
#include <raw.h>
#include <edmac.h>
#endif
#include "mirror_photo_probe.h"
#include "fx_mirror_raw.h"
#include "gl_format.h"
#define MAX_PHOTO_BYTES (0x1f24000u-0x1000u)
static struct {
    mirror_photo_report r;
    unsigned gui,epoch,exposure[4],seen;
    int log_pending,writing;
    fx_mirror_raw mapped,identity;
} photo;
static unsigned lock(void){unsigned s=cli();__asm__ __volatile__("" ::: "memory");return s;}
static void unlock(unsigned s){__asm__ __volatile__("" ::: "memory");sei(s);}
static uintptr_t canonical(uintptr_t p){return (uintptr_t)CACHEABLE((void*)p);}
static void signal_locked(unsigned kind,unsigned value,unsigned length,unsigned extra)
{
    if(photo.r.stage!=MP_ARMED&&photo.r.stage!=MP_WAIT_QR&&photo.r.stage!=MP_RECHECK)return;
    if(photo.r.events<32)photo.r.event[photo.r.events++]=(mirror_photo_event){get_ms_clock(),kind,value,length,extra};
    else{photo.r.event[photo.r.event_dropped%32]=(mirror_photo_event){get_ms_clock(),kind,value,length,extra};photo.r.event_dropped++;}
}
void mirror_photo_signal(unsigned kind,unsigned value,unsigned length,unsigned extra)
{unsigned s=lock();signal_locked(kind,value,length,extra);unlock(s);}
void mirror_photo_gui(unsigned state){unsigned s=lock();photo.gui=state;photo.epoch++;signal_locked(1,state,4,photo.epoch);unlock(s);}
void mirror_photo_property(unsigned which,unsigned value)
{if(which<4){unsigned s=lock();photo.exposure[which]=value;photo.seen|=1u<<which;unlock(s);}}
int mirror_photo_start(const fx_state*delivered)
{
    unsigned s=lock();
    if(photo.r.stage==MP_ARMED||photo.r.stage==MP_WAIT_QR||photo.r.stage==MP_RECHECK||photo.log_pending||photo.writing){unlock(s);return 0;}
    unsigned id=photo.r.request_id+1;memset(&photo.r,0,sizeof(photo.r));photo.r.request_id=id;
    photo.r.request_kind=2;photo.r.request_ms=get_ms_clock();photo.r.request_epoch=photo.epoch;
    memcpy(photo.r.request_exposure,photo.exposure,sizeof(photo.exposure));
    if(delivered&&delivered->initialized){photo.r.params=delivered->params;photo.r.preview_ms=delivered->last_ms;
        photo.r.stage=MP_WAIT_QR;}
    else{photo.r.stage=MP_FAILED;photo.r.error=MP_NO_PREVIEW;photo.log_pending=1;}
    unlock(s);return 1;
}
void mirror_photo_status(mirror_photo_report*out){if(out){unsigned s=lock();*out=photo.r;unlock(s);}}
static void finish(unsigned error)
{unsigned s=lock();photo.r.error=error;photo.r.stage=error?MP_FAILED:MP_DONE;photo.log_pending=1;unlock(s);}
void mirror_photo_cancel(void)
{if(photo.r.stage==MP_WAIT_QR||photo.r.stage==MP_RECHECK)finish(MP_CANCELLED);}
static int same_source(void)
{
    const gl_frame*f=&photo.mapped.source;
    unsigned before=edmac_get_state(0);uintptr_t address=canonical(edmac_get_address(0)),pointer=canonical(edmac_get_pointer(0));
    unsigned after=edmac_get_state(0);
    return !before&&!after&&!lv&&gui_state==3&&canonical((uintptr_t)raw_info.buffer)==photo.r.buffer&&
        raw_info.width==(int)f->width&&raw_info.height==(int)f->height&&raw_info.pitch==(int)f->pitch&&
        raw_info.frame_size==(int)f->size&&raw_info.bits_per_pixel==14&&
        address==photo.r.dma_address&&pointer==photo.r.dma_pointer;
}
static unsigned hash(unsigned v,unsigned sample){return (v^sample)*16777619u;}
static int sample(int recheck)
{
    if(!same_source())return MP_CHANGED;
    unsigned a=2166136261u,b=a;
    for(unsigned i=0;i<64;i++){
        uint16_t original,mapped;
        if(fx_mirror_raw_sample(&photo.identity,photo.r.x[i],photo.r.y[i],&original)||
           fx_mirror_raw_sample(&photo.mapped,photo.r.x[i],photo.r.y[i],&mapped))return MP_CHANGED;
        a=hash(a,original);b=hash(b,mapped);
        if(!recheck){photo.r.source_values[i]=original;photo.r.mapped_values[i]=mapped;}
        else if(photo.r.source_values[i]!=original||photo.r.mapped_values[i]!=mapped)return MP_CHANGED;
    }
    if(!same_source())return MP_CHANGED;
    if(!recheck){photo.r.source_hash=a;photo.r.mapped_hash=b;}
    else photo.r.stable_samples=1;
    return MP_OK;
}
static int prepare(void)
{
    photo.r.mode=(unsigned)shooting_mode;photo.r.job=lens_info.job_state;
    if(lv)return MP_LV_ACTIVE; /* raw_update_params would otherwise choose LV. */
    if(!can_use_raw_overlays_photo())return MP_NOT_RAW;
    if(!raw_update_params())return MP_RAW_SETUP;
    struct raw_info r=raw_info;
    photo.r.width=(unsigned)r.width;photo.r.height=(unsigned)r.height;photo.r.pitch=(unsigned)r.pitch;
    photo.r.bytes=(unsigned)r.frame_size;photo.r.bits=(unsigned)r.bits_per_pixel;
    photo.r.black=(unsigned)r.black_level;photo.r.white=(unsigned)r.white_level;photo.r.cfa=(unsigned)r.cfa_pattern;
    photo.r.buffer=canonical((uintptr_t)r.buffer);
    if(r.width<=0||r.width>8192||r.height<=0||r.height>8192||r.pitch<=0||r.frame_size<=0||r.bits_per_pixel!=14||(r.width&7)||
        (uint64_t)(unsigned)r.width*(unsigned)r.height<10000000u||r.frame_size>(int)MAX_PHOTO_BYTES||
        (uint64_t)(unsigned)r.pitch*(unsigned)r.height!=(unsigned)r.frame_size||r.pitch!=r.width*14/8||
        !r.buffer||r.active_area.x1<0||r.active_area.y1<0||r.active_area.x2>r.width||r.active_area.y2>r.height||
        r.active_area.x2<=r.active_area.x1||r.active_area.y2<=r.active_area.y1||
        r.jpeg.x<0||r.jpeg.y<0||r.jpeg.width<2||r.jpeg.height<2||
        (uint64_t)(unsigned)r.jpeg.x+(unsigned)r.jpeg.width>(unsigned)(r.active_area.x2-r.active_area.x1)||
        (uint64_t)(unsigned)r.jpeg.y+(unsigned)r.jpeg.height>(unsigned)(r.active_area.y2-r.active_area.y1))return MP_GEOMETRY;
#ifndef FX_PHOTO_HOST_TEST
    if(photo.r.buffer<0x1000u||photo.r.buffer>0x20000000u-(unsigned)r.frame_size||(photo.r.buffer&3))return MP_GEOMETRY;
#endif
    for(unsigned i=0;i<4;i++)photo.r.active[i]=(unsigned)r.dng_active_area[i];
    photo.r.crop[0]=(unsigned)r.jpeg.x;photo.r.crop[1]=(unsigned)r.jpeg.y;
    photo.r.crop[2]=(unsigned)r.jpeg.width;photo.r.crop[3]=(unsigned)r.jpeg.height;
    photo.r.dma_state=edmac_get_state(0);photo.r.dma_address=canonical(edmac_get_address(0));photo.r.dma_pointer=canonical(edmac_get_pointer(0));
    if(photo.r.dma_state||photo.r.dma_address!=photo.r.buffer||photo.r.dma_pointer!=photo.r.buffer+(unsigned)r.frame_size)return MP_DMA;
    gl_frame f={UNCACHEABLE(r.buffer),(size_t)r.frame_size,(unsigned)r.width,(unsigned)r.height,(unsigned)r.pitch,GL_CANON14,(unsigned)r.black_level,(unsigned)r.white_level};
    uint32_t region[4]={(unsigned)(r.active_area.y1+r.jpeg.y),(unsigned)(r.active_area.x1+r.jpeg.x),
        (unsigned)(r.active_area.y1+r.jpeg.y+r.jpeg.height),(unsigned)(r.active_area.x1+r.jpeg.x+r.jpeg.width)};
    if(fx_mirror_raw_prepare(&photo.mapped,&f,region,&photo.r.params,&ml_shutdown_requested))return MP_GEOMETRY;
    fx_params identity={{90,2,500,500}};uint32_t tiny[4]={0,0,2,2};
    if(fx_mirror_raw_prepare(&photo.identity,&f,tiny,&identity,&ml_shutdown_requested))return MP_GEOMETRY;
    for(unsigned i=0;i<64;i++){
        unsigned cell=i/4,x=cell%4,y=cell/4;
        photo.r.x[i]=(uint16_t)(photo.mapped.left+(((photo.mapped.right-photo.mapped.left-2)*x/3)&~1u)+(i&1));
        photo.r.y[i]=(uint16_t)(photo.mapped.top+(((photo.mapped.bottom-photo.mapped.top-2)*y/3)&~1u)+((i>>1)&1));
    }
    unsigned s=lock();memcpy(photo.r.sample_exposure,photo.exposure,sizeof(photo.exposure));photo.r.exposure_seen=photo.seen;unlock(s);
    return sample(0);
}
static int text(FILE*f,const char*s){size_t n=strlen(s);return FIO_WriteFile(f,s,n)==(int)n;}
static void write_log_body(void)
{
    if(ml_shutdown_requested)return;
    if(!is_dir("ML/LOGS")&&FIO_CreateDirectory("ML/LOGS")){photo.r.error=MP_LOG;photo.r.stage=MP_FAILED;return;}
    char path[64],line[256];unsigned n;uint32_t bytes;
    for(n=0;n<1000;n++){gl_snprintf(path,sizeof(path),"ML/LOGS/MRAW%03u.LOG",n);if(FIO_GetFileSize(path,&bytes))break;}
    if(n==1000){photo.r.error=MP_LOG;photo.r.stage=MP_FAILED;return;}
    FILE*f=FIO_CreateFile(path);if(!f){photo.r.error=MP_LOG;photo.r.stage=MP_FAILED;return;}
    mirror_photo_report*r=&photo.r;
    int ok=text(f,"Mirror shutter observation and RAW source probe / EOSM202 / ML ed3e7c0\nRead-only samples; no owned RAW lease, no mirrored DNG saved\n");
    gl_snprintf(line,sizeof(line),"stage=%u error=%u request=%u request_ms=%u preview_ms=%u qr_ms=%u read_ms=%u recheck_ms=%u polls=%u\n",r->stage,r->error,r->request_id,r->request_ms,r->preview_ms,r->qr_ms,r->read_ms,r->recheck_ms,r->polls);if(ok)ok=text(f,line);
    gl_snprintf(line,sizeof(line),"request_epoch=%u observed_epoch=%u gui_states=%x lv_states=%x mode=%u job=%u\n",r->request_epoch,r->observed_epoch,r->gui_states,r->lv_states,r->mode,r->job);if(ok)ok=text(f,line);
    gl_snprintf(line,sizeof(line),"request_kind=%u events=%u dropped=%u\n",r->request_kind,r->events,r->event_dropped);if(ok)ok=text(f,line);
    for(unsigned i=0;ok&&i<r->events;i++){
        mirror_photo_event*e=&r->event[(r->event_dropped+i)%32];gl_snprintf(line,sizeof(line),"event_ms=%u kind=%u value=%x length=%u extra=%x\n",e->ms,e->kind,e->value,e->length,e->extra);ok=text(f,line);
    }
    gl_snprintf(line,sizeof(line),"width=%u height=%u pitch=%u bytes=%u bits=%u buffer=%x dma_state=%u dma_address=%x dma_pointer=%x\n",r->width,r->height,r->pitch,r->bytes,r->bits,(unsigned)r->buffer,r->dma_state,(unsigned)r->dma_address,(unsigned)r->dma_pointer);if(ok)ok=text(f,line);
    gl_snprintf(line,sizeof(line),"active=%u,%u,%u,%u crop=%u,%u,%u,%u black=%u white=%u cfa=%x\n",r->active[0],r->active[1],r->active[2],r->active[3],r->crop[0],r->crop[1],r->crop[2],r->crop[3],r->black,r->white,r->cfa);if(ok)ok=text(f,line);
    gl_snprintf(line,sizeof(line),"params=%u,%u,%u,%u exposure_request=%u,%u,%u,%u exposure_sample=%u,%u,%u,%u seen=%x\n",r->params.value[0],r->params.value[1],r->params.value[2],r->params.value[3],r->request_exposure[0],r->request_exposure[1],r->request_exposure[2],r->request_exposure[3],r->sample_exposure[0],r->sample_exposure[1],r->sample_exposure[2],r->sample_exposure[3],r->exposure_seen);if(ok)ok=text(f,line);
    gl_snprintf(line,sizeof(line),"source_hash=%x mapped_hash=%x stable_samples=%u\n",r->source_hash,r->mapped_hash,r->stable_samples);if(ok)ok=text(f,line);
    for(unsigned i=0;ok&&i<64&&r->read_ms;i++){
        gl_snprintf(line,sizeof(line),"sample=%u x=%u y=%u source=%u mapped=%u\n",i,r->x[i],r->y[i],r->source_values[i],r->mapped_values[i]);ok=text(f,line);
    }
    FIO_CloseFile(f);if(ok)gl_snprintf(photo.r.log,sizeof(photo.r.log),"%s",path);
    else{photo.r.error=MP_LOG;photo.r.stage=MP_FAILED;}
}
static void write_log(void)
{
    unsigned s=lock();photo.writing=1;photo.log_pending=0;unlock(s);
    write_log_body();s=lock();photo.writing=0;unlock(s);
}
void mirror_photo_service(void)
{
    unsigned stage=photo.r.stage;
    if(stage==MP_WAIT_QR||stage==MP_RECHECK){
        unsigned now=get_ms_clock(),s=lock(),gui=photo.gui,epoch=photo.epoch;unlock(s);
        photo.r.polls++;photo.r.observed_epoch=epoch;
        if(gui<32)photo.r.gui_states|=1u<<gui;
        photo.r.lv_states|=1u<<(lv?1:0);
        if(ml_shutdown_requested)finish(MP_CANCELLED);
        else if(stage==MP_WAIT_QR){
            if(gui==3&&epoch!=photo.r.request_epoch){
                photo.r.qr_events++;if(!photo.r.qr_ms)photo.r.qr_ms=now;
                if(lv&&(unsigned)(now-photo.r.qr_ms)<300)return;
                int error=prepare();if(error)finish((unsigned)error);
                else{photo.r.read_ms=get_ms_clock();photo.r.stage=MP_RECHECK;}
            }else if((unsigned)(now-photo.r.request_ms)>60000)finish(MP_TIMEOUT);
        }else if(gui!=3||lv)finish(MP_NO_QR);
        else if((unsigned)(now-photo.r.read_ms)>=20){int error=sample(1);photo.r.recheck_ms=now;finish((unsigned)error);}
    }
    if(photo.log_pending)write_log();
}
