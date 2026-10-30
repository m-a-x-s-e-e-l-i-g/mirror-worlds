/* 70D.112 research contract, derived from ROM and simulated Canon CR2 output.
 * Not selected by the distributable Mirror module; not hardware validation. */
#ifndef MIRROR_70D_RAW_CONTRACT_H
#define MIRROR_70D_RAW_CONTRACT_H
#include <stdint.h>
enum { M70_WIDTH=5648, M70_HEIGHT=3720, M70_PITCH=9884, M70_BYTES=36768480 };
static const uint32_t m70_region[4]={60,156,3708,5628};
typedef struct {
    uint32_t source,job,context,caller,cpsr;
    uint32_t liveview,job_state,shutdown,state_before,state_after,flags,address,pointer;
    uint32_t xa,xb,xn,yb,ya,yn,off1a,off1b,off2a,off2b,off3;
} m70_binding;
static inline uint32_t m70_canonical(uint32_t address)
{
    address &= ~0x40000000u;
    return address>=0x1000u&&address<0x20000000u?address:0;
}
static inline int m70_binding_valid(const m70_binding *b)
{
    if(!b)return 0;
    uint32_t source=m70_canonical(b->source);
    return source && !(source&1) && source<=0x20000000u-M70_PITCH-M70_BYTES &&
        m70_canonical(b->job) && b->context==0x7c15c && b->caller==0xff15c4d0 &&
        (b->cpsr&0xffu)==0x13 && !b->liveview && b->job_state && !b->shutdown &&
        !b->state_before && !b->state_after && b->flags==0x20000000 &&
        m70_canonical(b->address)==source+M70_PITCH &&
        m70_canonical(b->pointer)==source+M70_PITCH+M70_BYTES &&
        b->xa==M70_PITCH && b->xb==M70_PITCH && b->xn==M70_HEIGHT-1 && !b->yb &&
        !b->ya && !b->yn && !b->off1a && !b->off1b && !b->off2a && !b->off2b && !b->off3;
}
#endif
