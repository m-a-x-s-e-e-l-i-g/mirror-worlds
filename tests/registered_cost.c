/* SPDX-License-Identifier: GPL-2.0-or-later
 * Deterministic QEMU instruction-clock comparison, NOT a camera benchmark.
 * VersatilePB SP804 is 1 MHz; icount shift=0 advances 1 ns/instruction.
 * The timer brackets only the kernel, excluding initialization/checksum/IO.
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fx_mirror_registered.h"
#include "fx_mirror_edges.h"
enum {W=5280,H=3528,PITCH=9240,SIZE=PITCH*H,WORK=2*PITCH};
static volatile uint32_t*const timer=(volatile uint32_t*)0x101e2000u;
static uint32_t clock_ticks(void){__asm__ __volatile__("":::"memory");return timer[1];}
int main(void)
{
    timer[2]=0;timer[0]=UINT32_MAX;timer[2]=0x82;
    unsigned char*owned=malloc(SIZE+32),*work=malloc(WORK+32);assert(owned&&work);
    const uint32_t region[]={64,84,3520,5268};
    const unsigned settings[][3]={{2,2,2},{4,2,2},{15,3,3}};
    for(unsigned c=0;c<3;c++){
        memset(owned,0xa7,SIZE+32);memset(work,0x6b,WORK+32);
        for(unsigned i=0;i<SIZE;i++)owned[16+i]=(unsigned char)((i*37)^(i>>7));
        gl_frame f={owned+16,SIZE,W,H,PITCH,GL_CANON14,0,16383};
        fx_params params={{FX_MIRROR_EDGES,settings[c][0],settings[c][1],settings[c][2]}};fx_mirror_raw m;
        assert(!fx_mirror_raw_prepare(&m,&f,region,&params,0));
        uint32_t start=clock_ticks();int result=fx_mirror_registered_apply(&m,f.data,SIZE,work+16,WORK);uint32_t end=clock_ticks();
        assert(!result&&start!=end);
        uint32_t checksum=2166136261u;for(unsigned i=0;i<SIZE;i++)checksum=(checksum^owned[16+i])*16777619u;
        for(unsigned i=0;i<16;i++)assert(owned[i]==0xa7&&owned[16+SIZE+i]==0xa7&&work[i]==0x6b&&work[16+WORK+i]==0x6b);
        printf("RAW_COST={\"mask\":%u,\"dx\":%u,\"dy\":%u,\"icount_ticks\":%u,\"checksum\":%u}\n",
            settings[c][0],settings[c][1],settings[c][2],(unsigned)(start-end),(unsigned)checksum);
    }
    free(work);free(owned);return 0;
}
