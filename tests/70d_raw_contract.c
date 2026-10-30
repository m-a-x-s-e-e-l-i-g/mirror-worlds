#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../targets/70D.112/research/raw_contract.h"
int main(void)
{
    m70_binding b={.source=0x5ca00064,.job=0x40e3c064,.context=0x7c15c,.caller=0xff15c4d0,.cpsr=0x60000013,
        .job_state=1,.flags=0x20000000,.address=0x1ca02700,.pointer=0x1ed131e0,
        .xa=M70_PITCH,.xb=M70_PITCH,.xn=M70_HEIGHT-1};
    assert(m70_binding_valid(&b));
    m70_binding good=b;
    /* Every nonzero readout/control/layout field is part of this contract. */
    for(unsigned i=0;i<sizeof(b)/4;i++){
        b=good;uint32_t words[sizeof(b)/4];memcpy(words,&b,sizeof(b));
        words[i]=words[i]?0:1;memcpy(&b,words,sizeof(b));
        assert(!m70_binding_valid(&b));
    }
    b=good;b.cpsr|=0x20;assert(!m70_binding_valid(&b));
    b=good;b.cpsr|=0x80;assert(!m70_binding_valid(&b));
    b=good;b.source=0x5ffff000;assert(!m70_binding_valid(&b));
    b=good;b.source|=1;assert(!m70_binding_valid(&b));
    b=good;b.pointer-=M70_PITCH;assert(!m70_binding_valid(&b));
    b=good;b.source&=~0x40000000;b.job&=~0x40000000;assert(m70_binding_valid(&b));
    assert((m70_region[0]|m70_region[1]|m70_region[2]|m70_region[3])%2==0);
    assert(m70_region[3]-m70_region[1]==5472 && m70_region[2]-m70_region[0]==3648);
    puts("70D readout contract: identity, state, flags, extent, layout, aliases and Bayer bounds passed");
}
