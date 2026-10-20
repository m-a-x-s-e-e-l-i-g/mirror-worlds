/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade).
 * Private CPU buffers only. No photo/SRM fallback, allocation or Canon calls. */
#ifndef FX_MEMORY_PLAN_H
#define FX_MEMORY_PLAN_H
#include <stdint.h>
#include <stddef.h>
#define FX_DMA_RESERVE (1536u*1024u)
#define FX_CPU_RESERVE (384u*1024u)
typedef struct {unsigned cpu_mask,dma_required,cpu_required;} fx_memory_plan;
/* Bits: committed canvas, retained snapshot, complete effect workspace.
 * Prefer all DMA when it fits; otherwise minimize bytes on regular malloc.
 * Total free bytes do not prove contiguous capacity or independent heaps.
 * The owner must check both reserves after EVERY successful allocation and
 * free all partial blocks through their original backend on failure. */
static inline int fx_memory_choose(const size_t bytes[3],int dma_free,int cpu_free,fx_memory_plan*out)
{
    if(!bytes||!out||dma_free<0)return 0;
    uint64_t best=UINT64_MAX;fx_memory_plan chosen={0};int found=0;
    for(unsigned mask=0;mask<8;mask++){
        uint64_t dma=0,cpu=0;int valid=1;
        for(unsigned i=0;i<3;i++){
            if(bytes[i]>4u*1024u*1024u||((mask&(1u<<i))&&!bytes[i])){valid=0;break;}
            if(mask&(1u<<i))cpu+=bytes[i];else dma+=bytes[i];
        }
        if(!valid||!bytes[0])continue;
        dma+=FX_DMA_RESERVE;if(cpu)cpu+=FX_CPU_RESERVE;
        if(dma>(unsigned)dma_free||(cpu&&(cpu_free<0||cpu>(unsigned)cpu_free)))continue;
        if(cpu<best){best=cpu;chosen=(fx_memory_plan){mask,(unsigned)dma,(unsigned)cpu};found=1;}
    }
    if(found)*out=chosen;
    return found;
}
#endif
