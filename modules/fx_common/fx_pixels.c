/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#include "fx_pixels.h"
#include "fx_copy.h"
#include <string.h>
static int overlap(const void *a,size_t an,const void *b,size_t bn)
{ uintptr_t x=(uintptr_t)a,y=(uintptr_t)b; return x<=y ? y-x<an : x-y<bn; }
static void copy_rows(void*destination,const void*source,unsigned first,unsigned count,unsigned width,unsigned pitch)
{
    unsigned char*d=(unsigned char*)destination+(size_t)first*pitch;
    const unsigned char*s=(const unsigned char*)source+(size_t)first*pitch;
    if(pitch==width*2){fx_copy_cpu(d,s,(size_t)count*pitch);return;}
    for(unsigned y=0;y<count;y++)fx_copy_cpu(d+(size_t)y*pitch,s+(size_t)y*pitch,width*2);
}
static void copy_slit(void*destination,const void*source,unsigned first,unsigned count,unsigned width,unsigned height,unsigned pitch,int vertical)
{
    if(!vertical){copy_rows(destination,source,first,count,width,pitch);return;}
    for(unsigned y=0;y<height;y++)fx_copy_cpu((char*)destination+(size_t)y*pitch+first*4,
        (const char*)source+(size_t)y*pitch+first*4,count*4);
}
int fx_slit_step(const fx_slit *old, fx_slit *next,const void *source,
    const void *history,void *destination,size_t capacity,uint32_t width,
    uint32_t height,uint32_t pitch,const uint32_t *old_times,
    uint32_t *new_times,const fx_slit_params *p,uint32_t now)
{
    if (!old||!next||!source||!history||!destination||!old_times||!new_times||!p||
        width<4||width>720||(width&1)||!height||height>480||pitch<width*2||pitch>4096||
        (uint64_t)pitch*height>capacity||p->direction>3||!p->speed||p->speed>720||
        !p->width||p->width>144) return FX_INVALID;
    size_t bytes=(size_t)pitch*height;
    /* Timestamp arrays always cover max(width/2,height), including axis changes. */
    unsigned time_count=width/2>height?width/2:height;
    size_t tb=time_count*sizeof(uint32_t);
    const void *ptr[]={old,next,source,history,destination,old_times,new_times,p};
    size_t len[]={sizeof(*old),sizeof(*next),bytes,bytes,bytes,tb,tb,sizeof(*p)};
    for(unsigned i=0;i<8;i++)for(unsigned j=i+1;j<8;j++)
        if(overlap(ptr[i],len[i],ptr[j],len[j]))return FX_INVALID;
    fx_slit n=*old;
    int reset=!n.initialized||n.width!=width||n.height!=height||n.params.direction!=p->direction;
    unsigned axis=p->direction<2?width/2:height;
    unsigned slit=p->direction<2?(p->width+1)/2:p->width;
    if(slit>axis)slit=axis;
    unsigned advance=0;
    if(reset){
        memset(&n,0,sizeof(n));n.initialized=1;n.width=width;n.height=height;
        for(unsigned i=0;i<time_count;i++)new_times[i]=now;
    }else{
        if(n.cursor>=axis||n.credit>=2000)return FX_INVALID;
        memcpy(new_times,old_times,tb);
        uint32_t dt=now-n.last_ms;
        if(dt>500){n.gaps++;n.paused_ms+=dt;dt=0;}
        unsigned denominator=p->direction<2?2000:1000;
        uint64_t distance=(uint64_t)dt*p->speed+n.credit;
        advance=(unsigned)(distance/denominator);n.credit=(unsigned)(distance%denominator);
    }
    unsigned count=advance>slit?advance:slit;
    if(count>axis)count=axis;
    /* A sweep is at most two contiguous runs, including wrap and reverse.
     * On initialization/full-axis replacement the source already supplies
     * every visible byte. Preserve row padding exactly as the original path. */
    copy_rows(destination,reset||count==axis?source:history,0,height,width,pitch);
    unsigned cursor=n.cursor,remaining=count;
    while(remaining){
        unsigned run=axis-cursor;if(run>remaining)run=remaining;
        unsigned first=p->direction&1?axis-cursor-run:cursor;
        for(unsigned i=0;i<run;i++)new_times[first+i]=now;
        if(!reset&&count<axis)copy_slit(destination,source,first,run,width,height,pitch,p->direction<2);
        remaining-=run;cursor=0;
    }
    n.cursor=(n.cursor+advance)%axis;n.last_ms=now;n.params=*p;n.frames++;
    *next=n;return FX_OK;
}
static void u16(unsigned char*p,unsigned v){p[0]=(unsigned char)v;p[1]=(unsigned char)(v>>8);}
static void u32(unsigned char*p,uint32_t v){u16(p,v);u16(p+2,v>>16);}
static void tag(unsigned char*h,unsigned i,unsigned id,unsigned type,unsigned count,uint32_t value)
{ unsigned char*p=h+10+i*12;u16(p,id);u16(p+2,type);u32(p+4,count);u32(p+8,value); }
static unsigned char clip(int v){return v<0?0:v>255?255:(unsigned char)v;}
int fx_tiff_write_ex(const void *source,size_t capacity,uint32_t width,
    uint32_t height,uint32_t pitch,void *workspace,size_t work_size,
    fx_write_fn write,void *context,volatile int *stop,const char *description)
{
    if(!source||!workspace||!write||!description||strlen(description)>160||width<4||width>720||(width&1)||!height||height>480||
       pitch<width*2||pitch>4096||(uint64_t)pitch*height>capacity||work_size<width*3||
       overlap(source,(size_t)pitch*height,workspace,width*3))return FX_INVALID;
    if(stop&&*stop)return FX_CANCEL;
    unsigned char h[512]={0};h[0]=h[1]='I';u16(h+2,42);u32(h+4,8);u16(h+8,13);
    tag(h,0,256,4,1,width);tag(h,1,257,4,1,height);tag(h,2,258,3,3,256);
    tag(h,3,259,3,1,1);tag(h,4,262,3,1,2);
    const char artist[]="Max Seelig (MAXmade)";
    unsigned description_size=(unsigned)strlen(description)+1;
    tag(h,5,270,2,description_size,320);tag(h,6,273,4,1,512);
    tag(h,7,274,3,1,1);tag(h,8,277,3,1,3);tag(h,9,278,4,1,height);
    tag(h,10,279,4,1,width*height*3);tag(h,11,284,3,1,1);tag(h,12,315,2,sizeof(artist),272);
    u16(h+256,8);u16(h+258,8);u16(h+260,8);
    memcpy(h+272,artist,sizeof(artist));memcpy(h+320,description,description_size);
    if(!write(context,h,sizeof(h)))return FX_IO;
    unsigned char *row=workspace;
    for(unsigned y=0;y<height;y++){
        if(stop&&*stop)return FX_CANCEL;
        const unsigned char *in=(const unsigned char*)source+(size_t)y*pitch;
        for(unsigned x=0;x<width;x+=2){
            int u=in[x*2]<128?in[x*2]:(int)in[x*2]-256;
            int v=in[x*2+2]<128?in[x*2+2]:(int)in[x*2+2]-256;
            for(unsigned k=0;k<2;k++){
                int yy=in[x*2+1+k*2];unsigned char*p=row+(x+k)*3;
                p[0]=clip(yy+1613*v/1024);p[1]=clip(yy-(192*u+479*v)/1024);p[2]=clip(yy+1900*u/1024);
            }
        }
        if(!write(context,row,width*3))return FX_IO;
    }
    return FX_OK;
}
int fx_tiff_write(const void *source,size_t capacity,uint32_t width,uint32_t height,
    uint32_t pitch,void *workspace,size_t work_size,fx_write_fn write,void *context,volatile int *stop)
{
    return fx_tiff_write_ex(source,capacity,width,height,pitch,workspace,work_size,write,context,stop,
        "Rendered temporal composite; preview resolution; not RAW");
}
