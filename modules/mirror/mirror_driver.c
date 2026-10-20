/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#include "fx_mirror.h"
#include "fx_mirror_edges.h"
#include "effect_config.h"
#include <string.h>
static int render(const fx_state*old,fx_state*next,const void*source,const void*history,void*dest,size_t cap,
    unsigned width,unsigned height,unsigned pitch,const uint32_t*times,uint32_t*new_times,
    const fx_params*p,unsigned now,void*workspace,size_t workspace_size)
{
    (void)history;(void)times;(void)new_times;
    int error=fx_mirror_render(source,dest,cap,workspace,workspace_size,p,width,height,pitch);
    if(error)return error;
    memset(next,0,sizeof(*next));next->params=*p;next->initialized=1;next->width=width;next->height=height;
    next->last_ms=now;next->frames=old->frames+1;return FX_OK;
}
const fx_effect FX(effect)={
    .module="mirror",.title="Mirror Worlds",.version=FX_VERSION,.prefix="MIR",.log_prefix="MIR",
#ifdef MIRROR_RELEASE
    .kind="native-edge-mirror",.description="Mirror Worlds edge reflections; native Canon CR2 capture",
    .param_count=4,.param_names={"mapping","edges","width_divisor","height_divisor"},
    .defaults={{FX_MIRROR_EDGES,FX_EDGE_RIGHT,2,2}},
#else
    /* The archived rendered-export fixture keeps its original identity. */
    .kind="native-centered-mirror",.description="Centered two-way mirror; native Canon CR2 capture",
    .param_count=4,.param_names={"axis_deg","reflections","center_x_per_mille","center_y_per_mille"},
    .defaults={{90,2,500,500}},
#endif
    .workspace_size=FX_MIRROR_MAX_WORKSPACE,
    .validate=fx_mirror_validate,.ready=fx_mirror_ready,.prepare=fx_mirror_prepare,.render=render,
};
