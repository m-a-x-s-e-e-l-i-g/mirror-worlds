/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade).
 * Bounded timestamped scene history; no heap/IO or mutable committed frames. */
#include "fx_fragment.h"
#include <string.h>
size_t fx_fragment_size(unsigned width,unsigned height)
{
    if(width<4||width>720||(width&3)||height<2||height>480||(height&1))return 0;
    return (size_t)9*width*height/2;
}
int fx_fragment_validate(const fx_params*p)
{
    return p&&p->value[0]>=24&&p->value[0]<=240&&!(p->value[0]&3)&&
        (!p->value[1]||(p->value[1]>=50&&p->value[1]<=500))&&p->value[2]<=100&&
        p->value[3]>=1&&p->value[3]<=65535;
}
int fx_fragment_ready(const void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch)
{
    size_t size=fx_fragment_size(width,height);
    return w&&size&&n>=size&&fx_fragment_validate(p)&&pitch>=width*2&&pitch<=4096;
}
int fx_fragment_prepare(void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch,volatile int*stop)
{
    if(!fx_fragment_ready(w,n,p,width,height,pitch))return FX_INVALID;
    return stop&&*stop?FX_CANCEL:FX_OK;
}
unsigned fx_fragment_tiles(const fx_params*p,unsigned width,unsigned height)
{
    if(!fx_fragment_validate(p)||!fx_fragment_size(width,height))return 0;
    return ((width+p->value[0]-1)/p->value[0])*((height+p->value[0]-1)/p->value[0]);
}
static uint32_t hash(uint32_t v)
{v^=v>>16;v*=0x7feb352du;v^=v>>15;v*=0x846ca68bu;v^=v>>16;return v;}
unsigned fx_fragment_age(const fx_params*p,unsigned column,unsigned row,unsigned columns)
{
    if(!fx_fragment_validate(p)||!columns)return 0;
    if(!p->value[1])return 0;
    uint32_t value=hash(p->value[3]^(row*columns+column)*0x9e3779b9u);
    return (value%100)<p->value[2]?((value>>8)&7):((column+row)&7);
}
static int overlap(const void*a,size_t an,const void*b,size_t bn)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x<=y?y-x<an:x-y<bn;}
static unsigned mean(unsigned a,unsigned b,unsigned c,unsigned d)
{return (a+b+c+d+2)/4;}
static void downsample(const unsigned char*source,unsigned char*dest,unsigned width,unsigned height,unsigned pitch)
{
    for(unsigned y=0;y<height;y+=2)for(unsigned x=0;x<width;x+=4){
        const unsigned char*a=source+(size_t)y*pitch+x*2,*b=a+pitch;
        unsigned char*d=dest+(size_t)(y/2)*width+x;
        d[1]=(unsigned char)mean(a[1],a[3],b[1],b[3]);d[3]=(unsigned char)mean(a[5],a[7],b[5],b[7]);
        d[0]=(unsigned char)(mean(a[0]^128,a[4]^128,b[0]^128,b[4]^128)^128);
        d[2]=(unsigned char)(mean(a[2]^128,a[6]^128,b[2]^128,b[6]^128)^128);
    }
}
int fx_fragment_step(const fx_state*old,fx_state*next,const void*source,void*destination,size_t capacity,
    void*workspace,size_t work_size,uint32_t*new_times,const fx_params*p,
    unsigned width,unsigned height,unsigned pitch,unsigned now)
{
    if(!old||!next||!source||!destination||!new_times||!fx_fragment_ready(workspace,work_size,p,width,height,pitch)||
        (uint64_t)pitch*height>capacity||old->data[0]>8||old->data[1]>8)return FX_INVALID;
    size_t bytes=(size_t)pitch*height,needed=fx_fragment_size(width,height),tb=fx_fragment_tiles(p,width,height)*4;
    const void*ptr[]={old,next,source,destination,workspace,new_times,p};
    const size_t len[]={sizeof(*old),sizeof(*next),bytes,bytes,needed,tb,sizeof(*p)};
    for(unsigned a=0;a<7;a++)for(unsigned b=a+1;b<7;b++)if(overlap(ptr[a],len[a],ptr[b],len[b]))return FX_INVALID;
    if(old->initialized){
        if(!old->data[0]||old->width!=width||old->height!=height)return FX_INVALID;
        unsigned used=1u<<old->data[1];
        for(unsigned i=0;i<old->data[0];i++){
            unsigned slot=old->data[12+i];if(slot>8||(used&(1u<<slot)))return FX_INVALID;used|=1u<<slot;
        }
    }
    fx_state n=*old;
    unsigned gap=old->initialized&&(unsigned)(now-old->last_ms)>500;
    unsigned reset=!old->initialized||gap||old->params.value[1]!=p->value[1];
    unsigned count=reset?0:old->data[0],elapsed=now-old->data[2];
    unsigned sample=reset||!p->value[1]||elapsed>=p->value[1];
    unsigned slot=old->data[1];size_t frame_bytes=(size_t)width*height/2;
    if(sample){
        /* Only the spare slot may change before the caller commits n. */
        downsample(source,(unsigned char*)workspace+slot*frame_bytes,width,height,pitch);
        if(!reset&&p->value[1]&&elapsed/p->value[1]>1)n.data[6]+=elapsed/p->value[1]-1;
        unsigned next_spare=count==8?old->data[19]:0;
        for(unsigned i=count<8?count:7;i>0;i--){n.data[12+i]=old->data[11+i];n.data[20+i]=old->data[19+i];}
        n.data[12]=slot;n.data[20]=now;n.data[0]=count<8?count+1:8;
        if(count<8){
            unsigned used=0;for(unsigned i=0;i<n.data[0];i++)used|=1u<<n.data[12+i];
            while(used&(1u<<next_spare))next_spare++;
        }
        n.data[1]=next_spare;n.data[2]=now;n.data[4]++;
    }
    if(reset){n.data[3]=now;n.data[5]+=(old->data[0]!=0);n.data[28]=0;}
    else if(memcmp(p,&old->params,sizeof(*p)))n.data[28]++;
    if(gap)n.data[11]+=now-old->last_ms;
    n.data[7]=(width+p->value[0]-1)/p->value[0];n.data[8]=(height+p->value[0]-1)/p->value[0];
    n.data[9]=n.data[20]-n.data[19+n.data[0]];n.data[30]=width/2;n.data[31]=height/2;
    const unsigned char*src=source;unsigned char*dst=destination;
    for(unsigned row=0;row<n.data[8];row++)for(unsigned col=0;col<n.data[7];col++){
        unsigned age=fx_fragment_age(p,col,row,n.data[7]);if(age>=n.data[0])age=n.data[0]-1;
        unsigned timestamp=n.data[20+age];
        int fresh=!p->value[1]||!fx_fragment_age(p,col,row,n.data[7])||(sample&&timestamp==now);
        new_times[row*n.data[7]+col]=fresh?now:timestamp;
        unsigned x0=col*p->value[0],y0=row*p->value[0];
        unsigned end_x=x0+p->value[0],end_y=y0+p->value[0];if(end_x>width)end_x=width;if(end_y>height)end_y=height;
        const unsigned char*history=(const unsigned char*)workspace+n.data[12+age]*frame_bytes;
        for(unsigned y=y0;y<end_y;y++){
            if(fresh)memcpy(dst+(size_t)y*pitch+x0*2,src+(size_t)y*pitch+x0*2,(end_x-x0)*2);
            else for(unsigned x=x0;x<end_x;x+=2){
                const unsigned char*h=history+(size_t)(y/2)*width+(x/4)*4;
                unsigned char*d=dst+(size_t)y*pitch+x*2;unsigned Y=h[(x&2)?3:1];
                d[0]=h[0];d[1]=(unsigned char)Y;d[2]=h[2];d[3]=(unsigned char)Y;
            }
        }
    }
    n.params=*p;n.initialized=1;n.width=width;n.height=height;n.last_ms=now;n.frames++;
    n.gaps+=gap;*next=n;return FX_OK;
}
