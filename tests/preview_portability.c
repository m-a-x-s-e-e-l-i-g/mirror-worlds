/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include "fx_sdk.h"
#include "fx_camera.h"
#include "fx_mirror_edges.h"
extern unsigned allocations,commits;
extern int menu_shown;
static unsigned reference(unsigned at,unsigned size,unsigned div,int low,int high)
{
    unsigned b=size/div;
    if(low&&at<b)return b+(b-at-1);
    if(high&&at>=size-b)return size-b-1-(at-(size-b));
    return at;
}
static void recovered_delivery(struct display_filter_buffers *buffers)
{
    fx_state state;memset(&state,0x5a,sizeof(state));fx_state untouched=state;
    /* Restoring a supported mode/query alone cannot resurrect an old frame. */
    assert(!fx_delivered_state(&state)&&!memcmp(&state,&untouched,sizeof(state)));
    assert(fx_filter(0)==1&&!fx_delivered_state(&state));
    fx_filter(buffers);assert(fx_delivered_state(&state)&&state.initialized);
}
static void mode_delivery(struct display_filter_buffers *buffers,int *mode,int invalid,int unchanged,size_t bytes)
{
    fx_state state;assert(fx_delivered_state(&state));
    int old=*mode;*mode=invalid;
    /* The shutter getter may run before the next filter query or service tick. */
    assert(!fx_delivered_state(&state));
    memset(buffers->dst_buf,0xa5,bytes);assert(!fx_filter(0));fx_filter(buffers);
    if(unchanged)for(size_t i=0;i<bytes;i++)assert(((uint8_t*)buffers->dst_buf)[i]==0xa5);
    *mode=old;recovered_delivery(buffers);
}
static void render_layout(unsigned height)
{
    size_t bytes=1440u*height;
    uint8_t *src=malloc(bytes+32),*out=malloc(bytes+32),*original=malloc(bytes);
    assert(src&&out&&original);
    memset(src,0x7b,bytes+32);
    for(size_t i=0;i<bytes;i++)src[i+16]=(uint8_t)((i*37)^(i>>7));
    memcpy(original,src+16,bytes);
    struct display_filter_buffers buffers={src+16,out+16};
    const unsigned masks[]={1,2,4,8,3,12,15};unsigned count=0;
    for(unsigned k=0;k<7;k++)for(unsigned dx=2;dx<=6;dx++)for(unsigned dy=2;dy<=6;dy++){
        unsigned mask=masks[k];
        if(!(mask&3)&&dx!=2)continue;
        if(!(mask&12)&&dy!=2)continue;
        if((mask&3)==3&&dx==2)continue;
        if((mask&12)==12&&dy==2)continue;
        fx_params p={{FX_MIRROR_EDGES,mask,dx,dy}};
        assert(fx_controls(&p));fx_service();assert(fx_filter(0)==1);
        memset(out,0xa5,bytes+32);fx_filter(&buffers);
        for(unsigned y=0;y<height;y++)for(unsigned x=0;x<360;x++){
            unsigned sy=reference(y,height,dy,mask&4,mask&8),sx=reference(x,360,dx,mask&1,mask&2);
            const uint8_t*s=src+16+sy*1440+sx*4;uint8_t*d=out+16+y*1440+x*4;
            assert(d[0]==s[0]&&d[2]==s[2]);assert(d[1]==s[x==sx?1:3]&&d[3]==s[x==sx?3:1]);
        }
        assert(!memcmp(src+16,original,bytes));
        for(unsigned i=0;i<16;i++)assert(out[i]==0xa5&&out[bytes+16+i]==0xa5);
        count++;
    }
    assert(count==44);
    mode_delivery(&buffers,&vram_lv.height,(int)height/2,1,bytes);
    mode_delivery(&buffers,&ext_monitor_hdmi,1,1,bytes);
    mode_delivery(&buffers,&lv_paused,1,1,bytes);
    mode_delivery(&buffers,&lv_dispsize,5,1,bytes);
    mode_delivery(&buffers,&lv,0,1,bytes);
    mode_delivery(&buffers,&sensor_cleaning,1,1,bytes);
    mode_delivery(&buffers,&ml_shutdown_requested,1,1,bytes);
    mode_delivery(&buffers,&menu_shown,1,0,bytes);
    fx_state state;assert(fx_delivered_state(&state));
    fx_canon_gui(1);fx_canon_gui(0);recovered_delivery(&buffers);
    assert(fx_key(MODULE_KEY_PRESS_SET)==1&&fx_key(MODULE_KEY_PLAY)==1&&fx_key(MODULE_KEY_PRESS_FULLSHUTTER)==1);
    assert(!fx_capture());
    free(src);free(out);free(original);
}
int main(void)
{
    fx_camera_init();assert(fx_native_capture_mode());fx_canon_gui(0);
    assert(fx_start());fx_service();render_layout(480);
    fx_stop();fx_service();assert(!allocations);
    vram_lv.height=240;assert(fx_start());fx_service();render_layout(240);
    fx_stop();fx_service();assert(!allocations&&commits==106);
    vram_lv.width=736;vram_lv.pitch=1472;assert(fx_start());fx_service();
    fx_status status;fx_status_get(&status);assert(!status.running&&status.error==12&&!allocations);
    puts("Preview: 44 layouts at 720x480 and 720x240, mode changes, controls and cleanup: PASS");
    puts("Delivery validity: 9 invalidation/resume cases at both LCD heights: PASS");return 0;
}
