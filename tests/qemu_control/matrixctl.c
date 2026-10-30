/* SPDX-License-Identifier: GPL-2.0-or-later; emulator test helper, never shipped. */
#include <module.h>
#include <dryos.h>
#include <config.h>
#include <menu.h>
#include <vram.h>
#include <lens.h>
#include <string.h>
#include "fx_effect.h"
#include "fx_mirror_registered.h"
/* Cross-module imports resolve through ML's real shared TinyCC loader. */
extern int mirror_controls(const fx_params *);
extern unsigned mirror_filter(void *);
extern int mirror_delivered_state(fx_state *);
extern void mirror_gate_automatic(unsigned);
extern void mirror_canon_gui(unsigned);
extern int GetFreeMemForMalloc(void);
extern void *__priv_malloc(size_t);
extern void __priv_free(void *);
extern void *__priv_shoot_malloc(size_t);
extern void __priv_shoot_free(void *);
CONFIG_INT("mirror.qemu.command",command,0);
CONFIG_INT("mirror.qemu.result",result,0);
CONFIG_INT("mirror.qemu.completed",completed,0);
CONFIG_INT("mirror.qemu.fixture_phase",fixture_phase,0);
CONFIG_INT("mirror.qemu.fixture_layouts",fixture_layouts,0);
CONFIG_INT("mirror.qemu.fixture_checked",fixture_checked,0);
CONFIG_INT("mirror.qemu.fixture_free",fixture_free,0);
CONFIG_INT("mirror.qemu.fixture_allocator",fixture_allocator,0);
CONFIG_INT("mirror.qemu.fixture_delivery_checks",fixture_delivery_checks,0);
CONFIG_INT("mirror.qemu.menu_status",menu_status,0);
CONFIG_INT("mirror.qemu.raw_cases",raw_cases,0);
CONFIG_INT("mirror.qemu.raw_checked",raw_checked,0);
CONFIG_INT("mirror.qemu.raw_negative",raw_negative,0);
static volatile int stopping,finished;
/* Read the real module update callback through ML's serialized menu API.
 * 1 OFF, 2 preparing, 3 preview-only, 4 native ready, 5 saving, 6 unavailable. */
static void observe_menu_status(void)
{
    struct menu_display_info info;
    char *value=menu_get_str_value_from_script("Shoot","Mirror Worlds",&info);
    menu_status=!value?0:!strcmp(value,"OFF")?1:!strcmp(value,"ON - Preparing")?2:
        !strcmp(value,"ON - Preview only")?3:!strcmp(value,"ON - Ready")?4:
        !strcmp(value,"ON - Saving")?5:6;
}
static unsigned reference(unsigned at,unsigned extent,unsigned div,unsigned low,unsigned high)
{
    unsigned border=extent/div;
    if(low&&at<border)return border+(border-at-1);
    if(high&&at>=extent-border)return extent-border-1-(at-(extent-border));
    return at;
}
/* Tiny owned Canon14 frame: exercises the linked ARM kernel through actual
 * cross-module loader symbols, with no Canon RAW buffer or shutter access. */
static unsigned raw_value(unsigned x,unsigned y,unsigned pattern)
{return ((y&1)*2+(x&1))*4096+(pattern?((x*123+y*317)^(x*y*71))&4095:4*x+12*y);}
static void raw_store(unsigned char*row,unsigned x,unsigned v)
{
    for(unsigned k=0;k<14;k++){
        unsigned bit=x*14+k,byte=(bit/16)*2+(15-bit%16)/8,mask=1u<<((15-bit%16)%8);
        row[byte]=(row[byte]&~mask)|((v&(1u<<(13-k)))?mask:0);
    }
}
static unsigned raw_load(const unsigned char*row,unsigned x)
{
    unsigned v=0;
    for(unsigned k=0;k<14;k++){unsigned bit=x*14+k,byte=(bit/16)*2+(15-bit%16)/8;v=(v<<1)|((row[byte]>>((15-bit%16)%8))&1);}
    return v;
}
static void raw_neighbors(unsigned p,unsigned begin,unsigned end,unsigned div,unsigned low,unsigned high,unsigned out[2])
{
    unsigned b=2*((end-begin)/2/div),s=p;
    if(low&&p<begin+b)s=2*(begin+b)-1-p;
    else if(high&&p>=end-b)s=2*(end-b)-1-p;
    unsigned delta=(s^p)&1,first=begin+(p&1),last=end-2+(p&1);
    int a=(int)s-(int)delta,c=(int)s+(int)delta;
    out[0]=a<(int)first?first:(unsigned)a;out[1]=c>(int)last?last:(unsigned)c;
}
static unsigned raw_expected(unsigned x,unsigned y,unsigned mask,unsigned dx,unsigned dy,unsigned pattern)
{
    if(x<4||x>=28||y<2||y>=22)return raw_value(x,y,pattern);
    unsigned xx[2],yy[2];raw_neighbors(x,4,28,dx,mask&1,mask&2,xx);raw_neighbors(y,2,22,dy,mask&4,mask&8,yy);
    unsigned a=(raw_value(xx[0],yy[0],pattern)+raw_value(xx[0],yy[1],pattern)+1)/2;
    unsigned b=(raw_value(xx[1],yy[0],pattern)+raw_value(xx[1],yy[1],pattern)+1)/2;
    return (a+b+1)/2;
}
static int raw_fixture(void)
{
    enum {W=32,H=24,PITCH=56,SIZE=PITCH*H,WORK=PITCH*2};
    unsigned char owned[SIZE+32],scratch[WORK+32];
    const unsigned masks[]={1,2,4,8,3,12,15};const uint32_t region[]={2,4,22,28};
    for(unsigned pattern=0;pattern<2;pattern++)for(unsigned k=0;k<7;k++)for(unsigned dx=2;dx<=6;dx++)for(unsigned dy=2;dy<=6;dy++){
        unsigned mask=masks[k];
        if((!(mask&3)&&dx!=2)||(!(mask&12)&&dy!=2)||((mask&3)==3&&dx==2)||((mask&12)==12&&dy==2))continue;
        memset(owned,0x95,sizeof(owned));memset(scratch,0x6b,sizeof(scratch));
        for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++)raw_store(owned+16+y*PITCH,x,raw_value(x,y,pattern));
        gl_frame f={owned+16,SIZE,W,H,PITCH,GL_CANON14,0,16383};fx_params params={{180,mask,dx,dy}};fx_mirror_raw m;
        if(fx_mirror_raw_prepare(&m,&f,region,&params,0)||fx_mirror_registered_workspace(&m)!=WORK||
           fx_mirror_registered_apply(&m,f.data,SIZE,scratch+16,WORK))return -30;
        for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++){
            raw_checked++;if(raw_load(owned+16+y*PITCH,x)!=raw_expected(x,y,mask,dx,dy,pattern))return -31;
        }
        for(unsigned i=0;i<16;i++)if(owned[i]!=0x95||owned[16+SIZE+i]!=0x95||scratch[i]!=0x6b||scratch[16+WORK+i]!=0x6b)return -32;
        raw_cases++;
    }
    unsigned v=raw_load(owned+16+2*PITCH,4);raw_store(owned+16+2*PITCH,4,v^1);
    raw_negative=raw_load(owned+16+2*PITCH,4)!=raw_expected(4,2,15,6,6,1);
    return raw_cases==88&&raw_negative?1:-33;
}
static int fixture(unsigned corrupt)
{
    struct vram_info *v=get_yuv422_vram();
    if(!v||v->width!=720||v->pitch!=1440||(v->height!=480&&v->height!=240))return -10;
    if(!mirror_filter(0))return -11;
    if(lens_info.job_state)return -18;
    unsigned height=v->height,bytes=1440*height;
    int free_now=GetFreeMemForMalloc();
    fixture_free=free_now;
    /* These CPU-only, temporary test buffers use the pinned core malloc
     * allocator's 384 KiB preferred reserve, not the DMA pool's reserve. */
    unsigned total=2*(bytes+32);void *arena=0;
    /* Explicit temporary photo-memory lease is confined to the unshipped
     * synthetic test. No Canon shutter is requested and the lease is freed
     * before the normal OFF/cleanup observation. Production Mirror never
     * falls back to this pool for its persistent preview canvas. */
    mirror_gate_automatic(0);
    if(free_now>=0&&(unsigned)free_now>=total+384u*1024u){fixture_allocator=1;arena=__priv_malloc(total);}
    else{fixture_allocator=2;arena=__priv_shoot_malloc(total);}
    unsigned char *src=arena,*dst=src?src+bytes+32:0;
    int outcome=-12,review_changed=0;
    if(!src||!dst)goto cleanup;
    memset(src,0x7b,bytes+32);
    for(unsigned i=0;i<bytes;i++)src[i+16]=(unsigned char)((i*37)^(i>>7));
    struct display_filter_buffers buffers={src+16,dst+16};
    /* Synthetic delivery must never be a reason to arm native photo mutation. */
    mirror_gate_automatic(0);
    unsigned masks[]={1,2,4,8,3,12,15};
    fx_state delivered;
    for(unsigned k=0;k<7;k++)for(unsigned dx=2;dx<=6;dx++)for(unsigned dy=2;dy<=6;dy++){
        unsigned mask=masks[k];
        if((!(mask&3)&&dx!=2)||(!(mask&12)&&dy!=2)||((mask&3)==3&&dx==2)||((mask&12)==12&&dy==2))continue;
        fx_params params={{180,mask,dx,dy}};
        outcome=-13;if(!mirror_controls(&params))goto cleanup;
        int ready=0;
        for(unsigned retry=0;retry<10&&!stopping;retry++){
            msleep(20);memset(dst,0xa5,bytes+32);mirror_filter(&buffers);
            if(mirror_delivered_state(&delivered)&&!memcmp(&delivered.params,&params,sizeof(params))){ready=1;break;}
        }
        outcome=-14;if(!ready)goto cleanup;
        if(corrupt)dst[47]^=1; /* Deliberately corrupt only this owned fixture output. */
        outcome=-15;
        for(unsigned y=0;y<height;y++)for(unsigned x=0;x<360;x++){
            unsigned sx=reference(x,360,dx,mask&1,mask&2),sy=reference(y,height,dy,mask&4,mask&8);
            const unsigned char*s=src+16+sy*1440+sx*4,*d=dst+16+y*1440+x*4;
            fixture_checked+=4;
            if(d[0]!=s[0]||d[2]!=s[2]||d[1]!=s[x==sx?1:3]||d[3]!=s[x==sx?3:1])goto cleanup;
        }
        outcome=-16;
        for(unsigned i=0;i<bytes;i++)if(src[i+16]!=(unsigned char)((i*37)^(i>>7)))goto cleanup;
        for(unsigned i=0;i<16;i++)if(dst[i]!=0xa5||dst[bytes+16+i]!=0xa5||src[i]!=0x7b||src[bytes+16+i]!=0x7b)goto cleanup;
        fixture_layouts++;
    }
    outcome=-19;mirror_canon_gui(1);review_changed=1;
    if(mirror_delivered_state(&delivered))goto cleanup;
    fixture_delivery_checks++;
    outcome=-20;mirror_canon_gui(0);review_changed=0;
    if(mirror_delivered_state(&delivered))goto cleanup;
    fixture_delivery_checks++;
    outcome=-21;mirror_filter(&buffers);
    if(!mirror_delivered_state(&delivered))goto cleanup;
    fixture_delivery_checks++;
    outcome=fixture_layouts==44?raw_fixture():-17;
cleanup:
    if(review_changed)mirror_canon_gui(0);
    if(arena){if(fixture_allocator==1)__priv_free(arena);else __priv_shoot_free(arena);}
    return outcome;
}
static void worker(void *unused)
{
    (void)unused;
    while(!stopping){
        unsigned request=(unsigned)command;command=0;
        if(request==0x4d570001u||request==0x4d570002u){
            result=menu_set_value_from_script("Shoot","Mirror Worlds",request==0x4d570001u);
            completed=(int)request;
            DryosDebugMsg(0,15,"MATRIXCTL completed=%x result=%d",request,result);
        }
        if(request==0x4d570003u||request==0x4d570004u){
            fixture_layouts=fixture_checked=fixture_delivery_checks=raw_cases=raw_checked=raw_negative=0;fixture_phase=1;completed=0;
            result=fixture(request==0x4d570004u);fixture_phase=result==1?2:3;
            completed=(int)request;
            DryosDebugMsg(0,15,"MATRIXCTL fixture=%x result=%d layouts=%d bytes=%d",request,result,fixture_layouts,fixture_checked);
        }
        observe_menu_status();msleep(100);
    }
    finished=1;
}
static unsigned init(void)
{
    stopping=finished=command=result=completed=fixture_phase=fixture_layouts=fixture_checked=fixture_free=fixture_allocator=fixture_delivery_checks=0;
    menu_status=raw_cases=raw_checked=raw_negative=0;
    unsigned task=task_create("matrix_control",0x1e,0x4000,worker,0);
    return !task||task==0xffffffffu;
}
static unsigned deinit(void)
{
    stopping=1;for(unsigned i=0;i<100&&!finished;i++)msleep(20);return !finished;
}
MODULE_INFO_START() MODULE_LONGNAME("QEMU matrix control") MODULE_INIT(init) MODULE_DEINIT(deinit) MODULE_INFO_END()
MODULE_CBRS_START() MODULE_CBRS_END()
MODULE_PROPHANDLERS_START() MODULE_PROPHANDLERS_END()
MODULE_CONFIGS_START() MODULE_CONFIG(command) MODULE_CONFIG(result) MODULE_CONFIG(completed)
    MODULE_CONFIG(fixture_phase) MODULE_CONFIG(fixture_layouts) MODULE_CONFIG(fixture_checked) MODULE_CONFIG(fixture_free)
    MODULE_CONFIG(fixture_allocator) MODULE_CONFIG(fixture_delivery_checks) MODULE_CONFIG(menu_status)
    MODULE_CONFIG(raw_cases) MODULE_CONFIG(raw_checked) MODULE_CONFIG(raw_negative) MODULE_CONFIGS_END()
