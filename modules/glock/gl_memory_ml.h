/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GL_MEMORY_ML_H
#define GL_MEMORY_ML_H
#include <stddef.h>
/* Exact exported wrappers from pinned src/mem.c. Persistent display pixels
 * cannot use fio_malloc: its temporary/SRM fallback can reserve Canon photo
 * pools across menu navigation or FA_CreateTestImage. Pair this allocator only
 * with its matching free, never __mem_free; allocation failure has no fallback.
 * Keep the same 1.5 MiB preferred reserve as the core AllocateMemory pool. */
extern void *__priv_alloc_dma_memory(size_t size);
extern void __priv_free_dma_memory(void *memory);
extern int GetFreeMemForAllocateMemory(void);
static inline void *gl_display_alloc(size_t size)
{
    int available = GetFreeMemForAllocateMemory();
    if (!size || size > 4u * 1024u * 1024u || available < 0 ||
        (size_t)available < size + 1536u * 1024u) return 0;
    return __priv_alloc_dma_memory(size);
}
static inline void gl_display_free(void *memory) { __priv_free_dma_memory(memory); }
#endif
