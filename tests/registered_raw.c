/* SPDX-License-Identifier: GPL-2.0-or-later
 * Independent, full-frame out-of-place oracle for the bounded in-place kernel.
 * No production pixel decoder, mapper or neighbor helper is used by the oracle.
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fx_mirror_registered.h"
#include "fx_mirror_edges.h"
enum {GUARD=32};
static volatile int stop_flag;
static unsigned plan_cancel,write_cancel,writes;
void FX(registered_plan_hook)(void){if(plan_cancel)stop_flag=1;}
void FX(registered_write_hook)(void){writes++;if(write_cancel)stop_flag=1;}
static unsigned load(const unsigned char*row,unsigned x)
{
    unsigned v=0;
    for(unsigned k=0;k<14;k++){
        unsigned bit=x*14+k,byte=(bit/16)*2+(15-bit%16)/8;
        v=(v<<1)|((row[byte]>>((15-bit%16)%8))&1);
    }
    return v;
}
static void store(unsigned char*row,unsigned x,unsigned v)
{
    for(unsigned k=0;k<14;k++){
        unsigned bit=x*14+k,byte=(bit/16)*2+(15-bit%16)/8,mask=1u<<((15-bit%16)%8);
        row[byte]=(row[byte]&~mask)|((v&(1u<<(13-k)))?mask:0);
    }
}
/* Place each axis on a sensor sample, so exact geometric reflection retains
 * CFA parity. Low axes sit at the last border sample; high axes at the first.
 * This is a uniform reflection for every color plane, not cell reversal. */
static int coordinate(unsigned p,unsigned begin,unsigned end,unsigned div,unsigned low,unsigned high)
{
    unsigned extent=2*(((end-begin)/2)/div);
    if(low&&p<begin+extent)return (int)(2*(begin+extent-1)-p);
    if(high&&p>=end-extent)return (int)(2*(end-extent)-p);
    return (int)p;
}
static void reference(unsigned char*out,const unsigned char*in,const fx_mirror_raw*m)
{
    unsigned w=m->source.width,h=m->source.height,pitch=m->source.pitch,mask=m->params.value[1];
    uint16_t*a=malloc((size_t)w*h*2);assert(a);
    memcpy(out,in,m->source.size);
    for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)a[y*w+x]=(uint16_t)load(in+y*pitch,x);
    for(unsigned y=m->top;y<m->bottom;y++)for(unsigned x=m->left;x<m->right;x++){
        int sx=coordinate(x,m->left,m->right,m->params.value[2],mask&1,mask&2);
        int sy=coordinate(y,m->top,m->bottom,m->params.value[3],mask&4,mask&8);
        assert(sx>=(int)m->left&&sx<(int)m->right&&sy>=(int)m->top&&sy<(int)m->bottom);
        assert(((unsigned)sx&1)==(x&1)&&((unsigned)sy&1)==(y&1));
        store(out+y*pitch,x,a[(unsigned)sy*w+(unsigned)sx]);
    }
    free(a);
}
static unsigned random_state=0x48207a19;
static unsigned next(void){random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
static unsigned signal(unsigned x,unsigned y,unsigned pattern)
{
    unsigned phase=(y&1)*2+(x&1);
    switch(pattern){
        case 0:return next()&16383;
        case 1:return phase*4096;
        case 2:return 512+phase*1024+4*x+12*y;
        case 3:return ((x/3+y/5)&1)?16383:0;
        case 4:return 16383;
        default:return 0;
    }
}
static void guards(const unsigned char*p,size_t n,unsigned value)
{for(unsigned i=0;i<GUARD;i++)assert(p[i]==value&&p[GUARD+n+i]==value);}
static unsigned cases,optical_samples,boundary_samples;
static void geometry(unsigned w,unsigned h,unsigned padding,const uint32_t region[4])
{
    unsigned pitch=w*14/8+padding;size_t size=(size_t)pitch*h,workspace=2*pitch;
    unsigned char*owned=malloc(size+2*GUARD),*original=malloc(size),*expected=malloc(size),*scratch=malloc(workspace+2*GUARD);
    assert(owned&&original&&expected&&scratch);
    const unsigned masks[]={1,2,4,8,3,12,15};
    for(unsigned pattern=0;pattern<6;pattern++){
        memset(original,0x95,size);
        for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)store(original+y*pitch,x,signal(x,y,pattern));
        unsigned layouts=0;
        for(unsigned k=0;k<7;k++)for(unsigned dx=2;dx<=6;dx++)for(unsigned dy=2;dy<=6;dy++){
            unsigned mask=masks[k];
            if((!(mask&3)&&dx!=2)||(!(mask&12)&&dy!=2)||((mask&3)==3&&dx==2)||((mask&12)==12&&dy==2))continue;
            memset(owned,0xa7,size+2*GUARD);memset(scratch,0x6b,workspace+2*GUARD);memcpy(owned+GUARD,original,size);
            gl_frame f={owned+GUARD,size,w,h,pitch,GL_CANON14,0,16383};fx_params params={{FX_MIRROR_EDGES,mask,dx,dy}};
            fx_mirror_raw m;stop_flag=0;plan_cancel=write_cancel=writes=0;
            assert(fx_mirror_raw_prepare(&m,&f,region,&params,&stop_flag)==FX_OK);
            fx_mirror_raw saved=m;assert(fx_mirror_registered_workspace(&m)==workspace);
            reference(expected,original,&m);
            assert(fx_mirror_registered_apply(&m,f.data,size,scratch+GUARD,workspace)==FX_OK);
            if(memcmp(f.data,expected,size)){
                fprintf(stderr,"Mismatch %ux%u pitch%u region%u,%u,%u,%u pattern%u mask%u dx%u dy%u\n",w,h,pitch,(unsigned)region[0],(unsigned)region[1],(unsigned)region[2],(unsigned)region[3],pattern,mask,dx,dy);
                for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)if(load((unsigned char*)f.data+y*pitch,x)!=load(expected+y*pitch,x)){
                    fprintf(stderr,"first pixel %u,%u got%u expected%u\n",x,y,load((unsigned char*)f.data+y*pitch,x),load(expected+y*pitch,x));abort();}
                abort();
            }
            assert(!memcmp(&saved,&m,sizeof(m)));guards(owned,size,0xa7);guards(scratch,workspace,0x6b);
            if(pattern==2)for(unsigned y=m.top;y<m.bottom;y++)for(unsigned x=m.left;x<m.right;x++){
                int sx=coordinate(x,m.left,m.right,dx,mask&1,mask&2),sy=coordinate(y,m.top,m.bottom,dy,mask&4,mask&8);
                if(sx==(int)m.left||sx+1==(int)m.right||sy==(int)m.top||sy+1==(int)m.bottom)boundary_samples++;
                assert(load((unsigned char*)f.data+y*pitch,x)==512+((y&1)*2+(x&1))*1024+4*(unsigned)sx+12*(unsigned)sy);
                optical_samples++;
            }
            cases++;layouts++;
        }
        assert(layouts==44);
    }
    free(scratch);free(expected);free(original);free(owned);
}
static void refusal_and_cancel(void)
{
    enum {W=32,H=24,PITCH=W*14/8,SIZE=PITCH*H,WORK=2*PITCH};
    unsigned char data[SIZE],before[SIZE],work[WORK],expected[SIZE];
    for(unsigned i=0;i<SIZE;i++)data[i]=(unsigned char)next();
    memcpy(before,data,SIZE);
    gl_frame f={data,SIZE,W,H,PITCH,GL_CANON14,0,16383};const uint32_t region[]={0,0,H,W};
    fx_params params={{FX_MIRROR_EDGES,15,3,3}};fx_mirror_raw m,bad;
    stop_flag=0;assert(!fx_mirror_raw_prepare(&m,&f,region,&params,&stop_flag));
#define REJECT(expr) do{assert((expr)==FX_INVALID);assert(!memcmp(data,before,SIZE));}while(0)
    assert(!fx_mirror_registered_workspace(0));REJECT(fx_mirror_registered_apply(0,data,SIZE,work,WORK));
    REJECT(fx_mirror_registered_apply(&m,data,SIZE-1,work,WORK));
    REJECT(fx_mirror_registered_apply(&m,data+1,SIZE-1,work,WORK));
    REJECT(fx_mirror_registered_apply(&m,data,SIZE,work,WORK-1));
    REJECT(fx_mirror_registered_apply(&m,data,SIZE,0,WORK));
    REJECT(fx_mirror_registered_apply(&m,data,SIZE,data,WORK));
    REJECT(fx_mirror_registered_apply(&m,data,SIZE,&m,sizeof(m)));
    REJECT(fx_mirror_registered_apply(&m,data,SIZE,work,SIZE_MAX));
    REJECT(fx_mirror_registered_apply(&m,data,SIZE_MAX,work,WORK));
    for(unsigned i=0;i<16;i++){
        bad=m;
        switch(i){
            case 0:bad.magic=0;break;case 1:bad.source.format=GL_U16;break;
            case 2:bad.source.pitch=PITCH-1;break;case 3:bad.source.size--;break;
            case 4:bad.source.width=8193;break;case 5:bad.source.height=8193;break;
            case 6:bad.params.value[0]=0;break;case 7:bad.params.value[1]=16;break;
            case 8:bad.params.value[2]=2;break;case 9:bad.params.value[3]=0;break;
            case 10:bad.left++;break;case 11:bad.bottom=H+2;break;
            case 12:bad.cells_w++;break;case 13:bad.cells_h++;break;
            case 14:bad.source.black=bad.source.white;break;
            case 15:bad.source.data=&bad;break;
        }
        assert(!fx_mirror_registered_workspace(&bad));REJECT(fx_mirror_registered_apply(&bad,data,SIZE,work,WORK));
    }
    bad=m;bad.stop=(volatile int*)data;REJECT(fx_mirror_registered_apply(&bad,data,SIZE,work,WORK));
    bad=m;bad.stop=(volatile int*)work;REJECT(fx_mirror_registered_apply(&bad,data,SIZE,work,WORK));
    stop_flag=1;assert(fx_mirror_registered_apply(&m,data,SIZE,work,WORK)==FX_CANCEL);assert(!memcmp(data,before,SIZE));
    stop_flag=0;plan_cancel=1;assert(fx_mirror_registered_apply(&m,data,SIZE,work,WORK)==FX_CANCEL);assert(!memcmp(data,before,SIZE));
    reference(expected,before,&m);stop_flag=0;plan_cancel=0;write_cancel=1;writes=0;
    assert(!fx_mirror_registered_apply(&m,data,SIZE,work,WORK));assert(stop_flag&&writes>1);assert(!memcmp(data,expected,SIZE));
    stop_flag=0;write_cancel=0;
    /* Workspace has byte alignment in the public contract. The optimized
     * decoder must retain a correct fallback for odd-address private storage. */
    unsigned char odd_storage[WORK+2];memset(odd_storage,0x6b,sizeof(odd_storage));
    unsigned char*odd=(unsigned char*)(((uintptr_t)odd_storage+1)|1);
    assert((uintptr_t)odd&1);memcpy(data,before,SIZE);
    assert(!fx_mirror_registered_apply(&m,data,SIZE,odd,WORK));assert(!memcmp(data,expected,SIZE));
    for(unsigned i=0;i<sizeof(odd_storage);i++)if(odd_storage+i<odd||odd_storage+i>=odd+WORK)assert(odd_storage[i]==0x6b);
    /* Horizontal-only processing checks cancellation after preparing its first
     * decoded row, and must not recheck after the first row has been written. */
    params=(fx_params){{FX_MIRROR_EDGES,2,2,2}};
    assert(!fx_mirror_raw_prepare(&m,&f,region,&params,&stop_flag));memcpy(data,before,SIZE);
    reference(expected,before,&m);plan_cancel=1;
    assert(fx_mirror_registered_apply(&m,data,SIZE,work,WORK)==FX_CANCEL);assert(!memcmp(data,before,SIZE));
    stop_flag=0;plan_cancel=0;write_cancel=1;writes=0;
    assert(!fx_mirror_registered_apply(&m,data,SIZE,work,WORK));assert(stop_flag&&writes>1);assert(!memcmp(data,expected,SIZE));
    stop_flag=0;write_cancel=0;
#undef REJECT
    puts("Registered RAW validation/cancel: malformed maps, overlaps, capacity, pre-write cancel and post-write completion PASS");
}
int main(void)
{
    /* Includes exact thirds, thirds with remainders, both packed-word phases,
     * odd requested boundaries (normalized by prepare), tiny/zero-width folds,
     * unaligned pitches and padding. */
    const unsigned shapes[][3]={{8,2,0},{8,8,3},{16,12,0},{24,18,8},{32,24,1},{40,30,2},{64,48,0},{72,54,4}};
    for(unsigned i=0;i<sizeof(shapes)/sizeof(shapes[0]);i++){
        unsigned w=shapes[i][0],h=shapes[i][1];uint32_t full[]={0,0,h,w};geometry(w,h,shapes[i][2],full);
        if(w>=24){uint32_t inset[]={1,3,h-1,w-3};geometry(w,h,shapes[i][2],inset);}
    }
    refusal_and_cancel();
    printf("REGISTERED_RAW={\"cases\":%u,\"optical_samples\":%u,\"boundary_samples\":%u,\"mismatches\":0,\"exact_source_samples\":true}\n",cases,optical_samples,boundary_samples);
    return 0;
}
