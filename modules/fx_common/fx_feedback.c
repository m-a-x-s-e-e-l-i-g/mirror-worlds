/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade).
 * Fixed-point affine flow and time-scaled decay. No heap, IO or trigonometric
 * imports in rendering. Previous high-precision history is never overwritten. */
#include "fx_feedback.h"
#include <string.h>
#define Q 16777216LL
static const int32_t log_retained[100]={
#include "fx_feedback_log.inc"
};
size_t fx_feedback_size(unsigned width,unsigned height)
{
    if(width<4||width>720||(width&3)||height<2||height>480||(height&1))return 0;
    return (size_t)width*height*3;
}
int fx_feedback_validate(const fx_params*p)
{
    return p&&p->value[0]>=50&&p->value[0]<=200&&p->value[1]<=120&&p->value[2]<=100&&
        p->value[3]<=240&&p->value[4]<=240;
}
int fx_feedback_ready(const void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch)
{
    size_t size=fx_feedback_size(width,height);
    return w&&!((uintptr_t)w&1)&&size&&n>=size&&fx_feedback_validate(p)&&pitch>=width*2&&pitch<=4096;
}
int fx_feedback_prepare(void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch,volatile int*stop)
{
    if(!fx_feedback_ready(w,n,p,width,height,pitch))return FX_INVALID;
    return stop&&*stop?FX_CANCEL:FX_OK;
}
static int32_t q16(int64_t value){return (int32_t)(value>=0?(value+128)/256:-((-value+128)/256));}
int fx_feedback_coefficients(const fx_params*p,unsigned dt,int32_t out[5])
{
    if(!fx_feedback_validate(p)||!out||dt>500)return FX_INVALID;
    int64_t a=-(int64_t)((int)p->value[0]-100)*dt*Q/100000;
    int64_t b=-(int64_t)((int)p->value[1]-60)*dt*292818/1000;
    int64_t vx=-(int64_t)((int)p->value[3]-120)*dt*Q/1000;
    int64_t vy=-(int64_t)((int)p->value[4]-120)*dt*Q/1000;
    int64_t tr=Q,ti=0,r=Q,i=0,x=0,y=0;
    /* Exponential of the affine generator, including integrated translation.
     * This composes the same flow for different callback intervals. */
    for(int n=1;n<=12;n++){
        x+=(tr*vx-ti*vy)/Q/n;y+=(ti*vx+tr*vy)/Q/n;
        int64_t nr=(tr*a-ti*b)/Q/n,ni=(ti*a+tr*b)/Q/n;
        tr=nr;ti=ni;r+=tr;i+=ti;
    }
    out[0]=q16(r);out[1]=q16(i);out[2]=q16(x/2);out[3]=q16(y/2);
    if(!dt||!p->value[2])out[4]=65536;
    else if(p->value[2]==100)out[4]=0;
    else{
        int64_t exponent=(int64_t)log_retained[p->value[2]]*dt/1000/8;
        int64_t term=Q,value=Q;
        for(int n=1;n<=10;n++){term=term*exponent/Q/n;value+=term;}
        for(int n=0;n<3;n++)value=(value*value+Q/2)/Q;
        out[4]=q16(value);
    }
    return FX_OK;
}
static int overlaps(const void*a,size_t an,const void*b,size_t bn)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x<=y?y-x<an:x-y<bn;}
static uint32_t lerp(uint32_t a,uint32_t b,unsigned fraction)
{return (a*(65536-fraction)+b*fraction+32768)>>16;}
static int sample(const uint16_t*old,unsigned width,unsigned height,int32_t x,int32_t y,uint32_t color[3])
{
    if(x<0||y<0||x>(int32_t)((width-1)*65536)||y>(int32_t)((height-1)*65536))return 0;
    unsigned ix=(unsigned)x>>16,iy=(unsigned)y>>16,fx=(unsigned)x&65535,fy=(unsigned)y&65535;
    unsigned nx=ix+1<width?ix+1:ix,ny=iy+1<height?iy+1:iy;
    const uint16_t*a=old+((size_t)iy*width+ix)*3,*b=old+((size_t)iy*width+nx)*3;
    const uint16_t*c=old+((size_t)ny*width+ix)*3,*d=old+((size_t)ny*width+nx)*3;
    for(unsigned k=0;k<3;k++)color[k]=lerp(lerp(a[k],b[k],fx),lerp(c[k],d[k],fx),fy);
    return 1;
}
static unsigned component(unsigned current,unsigned previous,unsigned weight)
{return (current*(65536-weight)+previous*weight+32768)>>16;}
int fx_feedback_step(const fx_state*old,fx_state*next,const void*source,void*destination,size_t capacity,
    void*workspace,size_t work_size,const fx_params*p,unsigned width,unsigned height,unsigned pitch,unsigned now)
{
    if(!old||!next||!source||!destination||!fx_feedback_ready(workspace,work_size,p,width,height,pitch)||
        (uint64_t)pitch*height>capacity||old->data[0]>1)return FX_INVALID;
    size_t bytes=(size_t)pitch*height,needed=fx_feedback_size(width,height);
    if(overlaps(old,sizeof(*old),next,sizeof(*next))||overlaps(next,sizeof(*next),p,sizeof(*p))||
       overlaps(source,bytes,destination,bytes)||overlaps(workspace,needed,source,bytes)||
       overlaps(workspace,needed,destination,bytes)||overlaps(workspace,needed,old,sizeof(*old))||
       overlaps(workspace,needed,next,sizeof(*next))||overlaps(workspace,needed,p,sizeof(*p))||
       overlaps(destination,bytes,old,sizeof(*old))||overlaps(destination,bytes,next,sizeof(*next))||
       overlaps(destination,bytes,p,sizeof(*p))||overlaps(source,bytes,next,sizeof(*next)))return FX_INVALID;
    if(old->initialized&&(old->width!=width||old->height!=height))return FX_INVALID;
    unsigned dt=now-old->last_ms,gap=old->initialized&&dt>500;
    int seed=!old->initialized||gap;
    int32_t flow[5]={65536,0,0,0,0};if(!seed)fx_feedback_coefficients(p,dt,flow);
    unsigned lw=width/2,lh=height/2,slot=1-old->data[0];size_t pixels=(size_t)lw*lh*3;
    const uint16_t*prior=(const uint16_t*)workspace+old->data[0]*pixels;
    uint16_t*future=(uint16_t*)workspace+slot*pixels;
    const unsigned char*src=source;unsigned char*dst=destination;
    int32_t row_x=((int32_t)(lw-1)*65536-flow[0]*(int32_t)(lw-1)+flow[1]*(int32_t)(lh-1))/2+flow[2];
    int32_t row_y=((int32_t)(lh-1)*65536-flow[1]*(int32_t)(lw-1)-flow[0]*(int32_t)(lh-1))/2+flow[3];
    for(unsigned y=0;y<lh;y++){
        int32_t px=row_x,py=row_y;
        for(unsigned x=0;x<lw;x++,px+=flow[0],py+=flow[1]){
            uint32_t color[3]={0,0,0};
            unsigned weight=!seed&&sample(prior,lw,lh,px,py,color)?(unsigned)flow[4]:0;
            uint32_t sums[3]={0,0,0};
            for(unsigned dy=0;dy<2;dy++){
                const unsigned char*s=src+(size_t)(y*2+dy)*pitch+x*4;
                unsigned char*d=dst+(size_t)(y*2+dy)*pitch+x*4;
                unsigned y0=component((unsigned)s[1]<<8,color[0],weight);
                unsigned y1=component((unsigned)s[3]<<8,color[0],weight);
                unsigned u=component((unsigned)(s[0]^128)<<8,color[1],weight);
                unsigned v=component((unsigned)(s[2]^128)<<8,color[2],weight);
                d[1]=(unsigned char)((y0+128)>>8);d[3]=(unsigned char)((y1+128)>>8);
                d[0]=(unsigned char)(((u+128)>>8)^128);d[2]=(unsigned char)(((v+128)>>8)^128);
                sums[0]+=y0+y1;sums[1]+=u;sums[2]+=v;
            }
            size_t index=((size_t)y*lw+x)*3;
            future[index]=(uint16_t)((sums[0]+2)/4);
            future[index+1]=(uint16_t)((sums[1]+1)/2);future[index+2]=(uint16_t)((sums[2]+1)/2);
        }
        row_x-=flow[1];row_y+=flow[0];
    }
    *next=*old;next->params=*p;next->initialized=1;next->width=width;next->height=height;next->last_ms=now;
    next->frames=seed?1:old->frames+1;next->gaps=old->gaps+gap;next->data[0]=slot;
    if(seed){
        next->data[1]=now;next->data[2]=1;next->data[3]=0;next->data[5]=0;
        next->data[10]=old->data[10]+(old->data[2]!=0);
    }else{
        next->data[2]++;next->data[3]+=dt;
        if(memcmp(p,&old->params,sizeof(*p)))next->data[5]++;
    }
    if(gap)next->data[4]+=dt;
    next->data[6]=seed?0:dt;next->data[7]=lw;next->data[8]=lh;next->data[9]=flow[4];
    return FX_OK;
}
