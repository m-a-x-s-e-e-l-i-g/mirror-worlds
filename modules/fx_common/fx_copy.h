/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef FX_COPY_H
#define FX_COPY_H
#include <stddef.h>
#include <stdint.h>
#include <string.h>
/* Non-overlapping normal RAM only. CPU copies, no DMA or ownership changes.
 * The pinned core memcpy64 loops over eight bytes. Move aligned runs in
 * 32-byte register bursts; keep the arbitrary-length/alignment fallback exact.
 * Cache publication remains the caller's existing responsibility. */
static inline void fx_copy_cpu(void *destination,const void *source,size_t size)
{
    if(!size)return;
#if defined(__arm__) && !defined(__thumb__)
    if(!(((uintptr_t)destination|(uintptr_t)source)&3)&&size>=32){
        unsigned char*d=destination;const unsigned char*s=source;size_t blocks=size/32;
        __asm__ __volatile__(
            "1:\n\t"
            "ldmia %1!, {r3-r10}\n\t"
            "stmia %0!, {r3-r10}\n\t"
            "subs %2, %2, #1\n\t"
            "bne 1b\n\t"
            : "+&r"(d), "+&r"(s), "+&r"(blocks)
            : : "r3","r4","r5","r6","r7","r8","r9","r10","cc","memory");
        size&=31;
        if(size)memcpy(d,s,size);
        return;
    }
#endif
    memcpy(destination,source,size);
}
#endif
