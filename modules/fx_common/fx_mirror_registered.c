/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#include "fx_mirror_registered.h"
#include "fx_mirror_edges.h"
#include "fx_copy.h"
#include <string.h>
#ifdef FX_REGISTERED_TEST_HOOK
extern void FX(registered_plan_hook)(void);
extern void FX(registered_write_hook)(void);
#endif
static uintptr_t address(const void*p)
{
#if defined(__arm__) || defined(FX_TEST_CANON_ALIASES)
    /* Same DIGIC V cache aliases as the existing native sensor primitives. */
    return (uintptr_t)p&~(uintptr_t)0x40000000u;
#else
    return (uintptr_t)p;
#endif
}
static int span(const void*p,size_t n)
{return p&&n&&(uintptr_t)p<=UINTPTR_MAX-n&&address(p)<=UINTPTR_MAX-n;}
static int overlap(const void*a,size_t an,const void*b,size_t bn)
{uintptr_t x=address(a),y=address(b);return x<=y?y-x<an:x-y<bn;}
static int prepare(const fx_mirror_raw*m,fx_mirror_raw*plan)
{
    if(!m||((uintptr_t)m&3)||m->magic!=0x524d4952u||m->source.format!=GL_CANON14||!fx_edges_valid(&m->params)||
       overlap(m,sizeof(*m),m->source.data,m->source.size))return 0;
    uint32_t region[4]={m->top,m->left,m->bottom,m->right};
    memset(plan,0,sizeof(*plan));
    if(fx_mirror_raw_prepare(plan,&m->source,region,&m->params,0))return 0;
    return m->left==plan->left&&m->right==plan->right&&m->top==plan->top&&m->bottom==plan->bottom&&
        m->cells_w==plan->cells_w&&m->cells_h==plan->cells_h&&(uint64_t)m->source.pitch*2<=SIZE_MAX;
}
size_t fx_mirror_registered_workspace(const fx_mirror_raw*m)
{fx_mirror_raw plan;return prepare(m,&plan)?(size_t)plan.source.pitch*2:0;}
static unsigned word(const unsigned char*p){return p[0]|((unsigned)p[1]<<8);}
static void put(unsigned char*p,unsigned v){p[0]=(unsigned char)v;p[1]=(unsigned char)(v>>8);}
static unsigned read14(const unsigned char*row,unsigned x)
{
    unsigned bit=x*14,shift=bit&15;row+=(bit/16)*2;unsigned a=word(row);
    return shift<=2?(a>>(2-shift))&16383:((a<<(shift-2))|(word(row+2)>>(18-shift)))&16383;
}
static void write14(unsigned char*row,unsigned x,unsigned v)
{
    unsigned bit=x*14,shift=bit&15;row+=(bit/16)*2;unsigned a=word(row);
    if(shift<=2){unsigned at=2-shift;put(row,(a&~(16383u<<at))|(v<<at));}
    else{unsigned low=16-shift,mask=(1u<<low)-1;put(row,(a&~mask)|(v>>(14-low)));
        unsigned b=word(row+2),at=low+2;mask=(1u<<(14-low))-1;put(row+2,(b&~(mask<<at))|((v&mask)<<at));}
}
typedef uint16_t alias16 __attribute__((may_alias));
typedef uint32_t alias32 __attribute__((may_alias));
/* Complete Canon14 groups avoid repeated neighboring-word read/modify/write.
 * Every group is read before publishing any of its eight output samples. */
static void unpack8(const unsigned char*s,alias16*v)
{
    unsigned a,b,c,d,e,f,g;
#if defined(__arm__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    if(!((uintptr_t)s&1)){
        /* Canon groups alternate word phase. Three aligned words plus one
         * halfword keep every read within this group's fourteen bytes. */
        if(!((uintptr_t)s&3)){
            unsigned u=((const alias32*)s)[0],v=((const alias32*)s)[1],w=((const alias32*)s)[2];
            a=u&65535;b=u>>16;c=v&65535;d=v>>16;e=w&65535;f=w>>16;g=((const alias16*)s)[6];
        }else{
            a=((const alias16*)s)[0];
            unsigned u=((const alias32*)(s+2))[0],v=((const alias32*)(s+2))[1],w=((const alias32*)(s+2))[2];
            b=u&65535;c=u>>16;d=v&65535;e=v>>16;f=w&65535;g=w>>16;
        }
    }else
#endif
    {a=word(s);b=word(s+2);c=word(s+4);d=word(s+6);e=word(s+8);f=word(s+10);g=word(s+12);}
    v[0]=(alias16)(a>>2);v[1]=(alias16)(((a&3)<<12)|(b>>4));
    v[2]=(alias16)(((b&15)<<10)|(c>>6));v[3]=(alias16)(((c&63)<<8)|(d>>8));
    v[4]=(alias16)(((d&255)<<6)|(e>>10));v[5]=(alias16)(((e&1023)<<4)|(f>>12));
    v[6]=(alias16)(((f&4095)<<2)|(g>>14));v[7]=(alias16)(g&16383);
}
static void pack8(unsigned char*d,const alias16*v)
{
    unsigned a=(v[0]<<2)|(v[1]>>12),b=(v[1]<<4)|(v[2]>>10),c=(v[2]<<6)|(v[3]>>8),
        e=(v[3]<<8)|(v[4]>>6),f=(v[4]<<10)|(v[5]>>4),g=(v[5]<<12)|(v[6]>>2),h=(v[6]<<14)|v[7];
#if defined(__arm__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    if(!((uintptr_t)d&1)){
        if(!((uintptr_t)d&3)){
            ((alias32*)d)[0]=(a&65535)|(b<<16);((alias32*)d)[1]=(c&65535)|(e<<16);
            ((alias32*)d)[2]=(f&65535)|(g<<16);((alias16*)d)[6]=(alias16)h;
        }else{
            ((alias16*)d)[0]=(alias16)a;((alias32*)(d+2))[0]=(b&65535)|(c<<16);
            ((alias32*)(d+2))[1]=(e&65535)|(f<<16);((alias32*)(d+2))[2]=(g&65535)|(h<<16);
        }
        return;
    }
#endif
    put(d,a);put(d+2,b);put(d+4,c);put(d+6,e);put(d+8,f);put(d+10,g);put(d+12,h);
}
static void copy_row(unsigned char*d,const unsigned char*s,unsigned left,unsigned right)
{
    if(d==s)return; /* The row on a pixel-centered fold is a fixed point. */
    unsigned x=left;
    for(;x<right&&(x&7);x++)write14(d,x,read14(s,x));
    unsigned end=right&~7u;
    if(end>x){
        size_t bytes=(end-x)*14u/8u;unsigned char*out=d+x*14u/8u;const unsigned char*in=s+x*14u/8u;
        if(!(((uintptr_t)out^(uintptr_t)in)&3))while(bytes&&((uintptr_t)out&3)){*out++=*in++;bytes--;}
        fx_copy_cpu(out,in,bytes);x=end;
    }
    for(;x<right;x++)write14(d,x,read14(s,x));
}
static void decode_row(alias16*out,const unsigned char*row,unsigned left,unsigned right)
{
    unsigned x=left;
    for(;x<right&&(x&7);x++)out[x]=(alias16)read14(row,x);
    for(;x+8<=right;x+=8)unpack8(row+x*14/8,out+x);
    for(;x<right;x++)out[x]=(alias16)read14(row,x);
}
static void decode_sources(alias16*out,const unsigned char*row,unsigned left,unsigned right,unsigned border,unsigned mask)
{
    /* The fixed axis sample and interior source band are copied verbatim.
     * Cache both source bands before either destination is written.
     * Merge touching bands; the unchanged center never needs decoding. */
    unsigned begin[2],end[2],count=0;
    if(mask&2){begin[count]=right-2*border+1;end[count++]=right-border+1;}
    if(mask&1){begin[count]=left+border-1;end[count++]=left+2*border-1;}
    if(count==2&&begin[0]>begin[1]){
        unsigned t=begin[0];begin[0]=begin[1];begin[1]=t;
        t=end[0];end[0]=end[1];end[1]=t;
    }
    if(count==2&&end[0]>=begin[1]){
        if(end[1]>end[0])end[0]=end[1];
        count=1;
    }
    for(unsigned i=0;i<count;i++)decode_row(out,row,begin[i],end[i]);
}
static void horizontal_cached(unsigned char*row,const alias16*source,unsigned left,unsigned right,unsigned border,unsigned mask)
{
    for(unsigned side=0;side<2;side++){
        if(!(mask&(1u<<side)))continue;
        unsigned begin=side?right-border:left,end=begin+border,pivot=side?right-border:left+border-1,x=begin;
        for(;x<end&&(x&7);x++)write14(row,x,source[2*pivot-x]);
        for(;x+8<=end;x+=8){
            unsigned sx=2*pivot-x;alias16 values[8];
            for(unsigned j=0;j<8;j++)values[j]=source[sx-j];
            pack8(row+x*14/8,values);
        }
        for(;x<end;x++)write14(row,x,source[2*pivot-x]);
    }
}
static int planning_stop(volatile int*stop)
{
#ifdef FX_REGISTERED_TEST_HOOK
    FX(registered_plan_hook)();
#endif
    return stop&&*stop;
}
int fx_mirror_registered_apply(const fx_mirror_raw*m,void*owned,size_t capacity,void*work,size_t work_bytes)
{
    fx_mirror_raw plan;
    if(!prepare(m,&plan))return FX_INVALID;
    size_t required=(size_t)plan.source.pitch*2;
    if(owned!=plan.source.data||capacity<plan.source.size||!span(owned,capacity)||!span(work,work_bytes)||work_bytes<required||
       overlap(owned,capacity,m,sizeof(*m))||overlap(work,work_bytes,owned,capacity)||overlap(work,work_bytes,m,sizeof(*m))||
       (m->stop&&(overlap((const void*)m->stop,sizeof(*m->stop),owned,capacity)||overlap((const void*)m->stop,sizeof(*m->stop),work,work_bytes))))return FX_INVALID;
    volatile int*stop=m->stop;
    if(stop&&*stop)return FX_CANCEL;
    unsigned pitch=plan.source.pitch,mask=plan.params.value[1];
    unsigned vertical=2*(plan.cells_h/plan.params.value[3]);
    unsigned horizontal=2*(plan.cells_w/plan.params.value[2]);
    unsigned char*data=owned,*cache=work;
    int started=vertical&&(mask&12);
    if((started||!horizontal||!(mask&3))&&planning_stop(stop))return FX_CANCEL;
    /* All validation precedes mutation. Cancellation may still stop the first
     * horizontal row's decode; after a first store the complete frame finishes. */
    if(vertical)for(unsigned side=0;side<2;side++){
        if(!(mask&(4u<<side)))continue;
        for(unsigned i=0;i<vertical;i++){
            unsigned y=side?plan.bottom-1-i:plan.top+i;
            unsigned pivot=side?plan.bottom-vertical:plan.top+vertical-1;
            unsigned sy=2*pivot-y;
            unsigned char*d=data+(size_t)y*pitch;
            copy_row(d,data+(size_t)sy*pitch,plan.left,plan.right);
#ifdef FX_REGISTERED_TEST_HOOK
            FX(registered_write_hook)();
#endif
        }
    }
    if(horizontal&&(mask&3))for(unsigned y=plan.top;y<plan.bottom;y++){
        unsigned char*row=data+(size_t)y*pitch;
        /* The retained two-packed-row lease holds one decoded 16-bit row;
         * no additional allocation/lease or resampling is needed.
         * Decode only the required source bands before any horizontal store. */
        if(!((uintptr_t)cache&1)){
            alias16*decoded=(alias16*)cache;decode_sources(decoded,row,plan.left,plan.right,horizontal,mask);
            if(!started){if(planning_stop(stop))return FX_CANCEL;started=1;}
            horizontal_cached(row,decoded,plan.left,plan.right,horizontal,mask);
        }else{
            /* Sources are in the untouched center or the fixed axis sample.
             * This also permits exact copies with byte-aligned workspace. */
            if(!started){if(planning_stop(stop))return FX_CANCEL;started=1;}
            for(unsigned side=0;side<2;side++){
                if(!(mask&(1u<<side)))continue;
                for(unsigned i=0;i<horizontal;i++){
                    unsigned x=side?plan.right-1-i:plan.left+i;
                    unsigned pivot=side?plan.right-horizontal:plan.left+horizontal-1;
                    unsigned sx=2*pivot-x;
                    write14(row,x,read14(row,sx));
                }
            }
        }
#ifdef FX_REGISTERED_TEST_HOOK
        FX(registered_write_hook)();
#endif
    }
    return FX_OK;
}
