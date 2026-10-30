/* A fragmented Canon DMA pool must be refused before its asserting allocator. */
#include <assert.h>
#include <stdio.h>
#include "gl_memory_ml.h"
static int free_bytes=16*1024*1024,max_region=16*1024*1024,query_error;
static unsigned requests,frees;
static char allocation;
int GetFreeMemForAllocateMemory(void){return free_bytes;}
int GetSizeOfMaxRegion(int *size){*size=max_region;return query_error;}
void *__priv_alloc_dma_memory(size_t size){(void)size;requests++;return &allocation;}
void __priv_free_dma_memory(void *memory){assert(memory==&allocation);frees++;}
int main(void)
{
    /* Actual QEMU failure: enough total space, no contiguous full-frame block. */
    free_bytes=0x19c438;max_region=0x8a04c;
    assert(!gl_display_alloc(691360)&&!requests);
    free_bytes=16*1024*1024;
    assert(!gl_display_alloc(691360)&&!requests); /* Plenty total, same fragmented max. */
    max_region=691360+1023;
    assert(!gl_display_alloc(691360)&&!requests);
    max_region=691360+1024;
    assert(gl_display_alloc(691360)==&allocation&&requests==1);
    gl_display_free(&allocation);assert(frees==1);
    query_error=1;assert(!gl_display_alloc(64)&&requests==1);
    query_error=0;max_region=0;assert(!gl_display_alloc(64)&&requests==1);
    max_region=16*1024*1024;free_bytes=1536*1024;
    assert(!gl_display_alloc(64)&&requests==1);
    free_bytes=16*1024*1024;
    assert(!gl_display_alloc(0)&&!gl_display_alloc(4u*1024u*1024u+1)&&requests==1);
    puts("Display allocation: fragmented pool, query failure, reserve and bounds: PASS");
}
