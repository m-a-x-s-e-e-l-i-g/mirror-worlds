#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <stdio.h>
int mirror_lj14_encode(const uint16_t*,uint32_t,uint32_t,uint8_t**,size_t*);
static void rejected(const uint16_t *pixels,uint32_t w,uint32_t h)
{
    uint8_t *out=(uint8_t*)(uintptr_t)1;size_t bytes=99;
    assert(mirror_lj14_encode(pixels,w,h,&out,&bytes)==-1);
    assert(!out&&!bytes);
}
int main(void)
{
    const uint16_t good[4]={0,16383,2,16380},bad[4]={0,16384,0,0};
    rejected(NULL,2,2);rejected(good,0,2);rejected(good,3,2);
    rejected(good,131072,1);rejected(good,2,0);rejected(good,2,65536);
    rejected(good,131070,65535);rejected(bad,2,2);
    assert(mirror_lj14_encode(good,2,2,NULL,NULL)==-1);
    puts("Lossless encoder bounds and 14-bit range: PASS");
    return 0;
}
