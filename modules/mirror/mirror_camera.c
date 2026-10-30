/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifdef MIRROR_CAMERA_HOST_TEST
#include "mirror_camera_sdk.h"
#else
#include <module.h>
#include <dryos.h>
#endif
#include "mirror_camera.h"
#include "mirror_raw_trace.h"
/* EOSM 2.0.2 only. Hook/readout values retained from the camera-tested 0.2.0 adapter.
 * A new backend needs its own verified hooks, geometry and ownership checks;
 * sharing a processor or sensor resolution is not sufficient. */
static const mirror_native_backend eosm202={
    .stage_pc=0xff3608d8u,
    .stage_words={0xe12fff1eu,0xe3a00000u,0xe12fff1eu,0xe12fff1eu},
    .stage_context=0x3f3d4u,.stage_caller=0xff152238u,.stage_job_offset=0xb4u,
    .stage_cpsr_mask=0xdfu,.stage_cpsr_value=0x13u,
    .points={
        {0xff1707e8u,{0xe5860058u,0xe5867088u,0xe5869070u,0xe5950094u},MT_RAW_SOURCE},
        {0xff1686d0u,{0xe5870058u,0xe587a070u,0xe587b088u,0xe5960050u},MT_SSS_SOURCE},
        {0xff429210u,{0xe92d407cu,0xe51f5edcu,0xe1a04000u,0xe5950004u},MT_PREPARE},
        {0xff4292b8u,{0xe92d4070u,0xe1a05000u,0xe51f0f88u,0xe3a04000u},MT_START},
        {0xff168128u,{0xe5860058u,0xe59d0000u,0xe2800b11u,0xe2800f41u},MT_JPEG_SOURCE},
        {0xff429280u,{0xe92d4070u,0xe1a05000u,0xe51f0f50u,0xe3a04000u},MT_PREPARE_JPEG},
        {0xff22dac0u,{0xe5900000u,0xe5922000u,0xe2811e25u,0xe1500002u},MT_JOB_GET},
        {0xff22da74u,{0xe92d4010u,0xe51f36f4u,0xe5902004u,0xe5900000u},MT_JOB_SET},
    },
    .point_count=8,.trace_start_pc=0xff4292b8u,.dma_kind=MIRROR_DMA_DIGIC5,
    .raw_desc=0x70340u,.sss_desc=0x6fce4u,.jpeg_desc=0x6fd8cu,
    .raw_context=0x40334u,.sss_context=0x4018cu,
    .alias_bit=0x40000000u,.origin_offset=0x4830u,
    .width=5280,.height=3528,.pitch=9240,.sensor_bytes=32598720u,
    .readout_offset=0x9060u,.readout_bytes=32607960u,.readout_xn=3528,.readout_flags=0,
    /* Full decoder-visible RAW area, including the image pixels outside
     * Canon's 5184x3456 JPEG crop (64,84)-(3520,5268). The owner CR2 and
     * LibRaw's EOS M geometry agree on 5208x3476 at (72,52). Leave the
     * optical-black top/left margins untouched. End coordinates exclude. */
    .region={52,72,3528,5280},
};
/* Explicit, unshipped research build only. Geometry/caller/DMA and transform
 * are verified in generated Canon CR2s; normal mirror.mo delivery/shutter
 * integration and physical-camera ownership remain unverified. */
#ifdef MIRROR_70D_RESEARCH
static const mirror_native_backend d70_112={
    .stage_pc=0xff361910u,
    .stage_words={0xe12fff1eu,0xe3a00000u,0xe12fff1eu,0xe12fff1eu},
    .stage_context=0x7c15cu,.stage_caller=0xff15c4d0u,.stage_job_offset=0xacu,
    .stage_cpsr_mask=0xffu,.stage_cpsr_value=0x13u,.source_alignment_mask=1,
    .points={
        {0xff2229b0u,{0xe5900000u,0xe5922000u,0xe2811e25u,0xe1500002u},MT_JOB_GET},
        {0xff222964u,{0xe92d4010u,0xe51f36f8u,0xe5902004u,0xe5900000u},MT_JOB_SET},
        {0xff41ea90u,{0xe92d4038u,0xe3a04000u,0xe3a03003u,0xe1a05000u},MT_BINDING_ONLY},
        {0xff437d58u,{0xe5940058u,0xe3500000u,0x0a00000du,0xe5940048u},MT_BINDING_ONLY},
        {0xff16ceb4u,{0xe5870058u,0xe5878070u,0xe587b088u,0xe5960044u},MT_BINDING_ONLY},
    },
    .point_count=5,.trace_start_pc=0xff437d58u,.dma_kind=MIRROR_DMA_DIGIC5,
    .alias_bit=0x40000000u,.origin_offset=9884,
    .width=5648,.height=3720,.pitch=9884,.sensor_bytes=36768480u,
    .readout_offset=9884,.readout_bytes=36768480u,.readout_xn=3719,.readout_flags=0x20000000u,
    .region={60,156,3708,5628},
};
#define MIRROR_70D_NATIVE (&d70_112)
#else
#define MIRROR_70D_NATIVE 0
#endif
typedef struct {
    const char *model,*firmware;
    const mirror_native_backend *native;
} camera_profile;
/* Current upstream 142472e: these DryOS ports enable CONFIG_DISPLAY_FILTERS.
 * This is a source-based preview candidate list, NOT hardware validation.
 * Other generations/ports must be audited before enabling them. */
static const camera_profile profiles[]={
    {"EOSM","2.0.2",&eosm202},
    {"5D2","2.1.2",0},{"5D3","1.1.3",0},{"5D3","1.2.3",0},
    {"6D","1.1.6",0},{"7D","2.0.3",0},{"50D","1.0.9",0},
    {"60D","1.1.1",0},{"70D","1.1.2",MIRROR_70D_NATIVE},{"100D","1.0.1",0},
    {"550D","1.0.9",0},{"600D","1.0.2",0},{"650D","1.0.4",0},
    {"700D","1.1.5",0},{"1100D","1.0.5",0},
};
static const camera_profile *selected;
int mirror_select_camera(void)
{
    selected=0;
    for(unsigned i=0;i<sizeof(profiles)/sizeof(profiles[0]);i++){
        if(is_camera(profiles[i].model,profiles[i].firmware)){
            selected=&profiles[i];return 1;
        }
    }
    return 0;
}
const char *mirror_camera_name(void){return selected?selected->model:"Unsupported";}
const mirror_native_backend *mirror_camera_native(void)
{
#ifdef MIRROR_PREVIEW_ONLY
    /* Older module APIs may provide display filters but no patch manager.
     * This separately built variant never exposes a native capture backend. */
    return 0;
#else
    return selected?selected->native:0;
#endif
}
int mirror_camera_dma(unsigned channel,mirror_dma_info *out)
{
#ifdef MIRROR_PREVIEW_ONLY
    (void)channel;(void)out;return 0;
#else
    /* Never call edmac_get_info: its struct-return size changes on DIGIC 8+.
     * Decode scalar shadow registers ONLY for an explicit DIGIC V backend.
     * Offsets/masks below are DIGIC V, matching core edmac.c. No MMIO writes. */
    const mirror_native_backend*backend=mirror_camera_native();
    if(!out||!backend||backend->dma_kind!=MIRROR_DMA_DIGIC5||channel>=32)return 0;
    extern uint32_t edmac_get_base(uint32_t channel);
    uint32_t base=edmac_get_base(channel);
    if(!base||base==UINT32_MAX)return 0;
    uint32_t a=shamem_read(base+0x14),b=shamem_read(base+0x10),n=shamem_read(base+0x0c);
    *out=(mirror_dma_info){
        .xa=a&65535,.ya=a>>16,.xb=b&65535,.yb=b>>16,.xn=n&65535,.yn=n>>16,
        .off1a=(uint32_t)((int32_t)(shamem_read(base+0x20)<<13)>>13),
        .off1b=(uint32_t)((int32_t)(shamem_read(base+0x18)<<13)>>13),
        .off2a=shamem_read(base+0x24),.off2b=shamem_read(base+0x1c),.off3=shamem_read(base+0x28),
    };
    return 1;
#endif
}
