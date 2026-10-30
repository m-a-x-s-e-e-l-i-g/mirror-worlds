/* Shared host SDK for renderer and preview-to-capture integration fixtures. */
#include <assert.h>
#include <stdlib.h>
#include "fx_sdk.h"
#include "fx_namespace.h"
int lv=1,lv_paused,lv_dispsize=1,ext_monitor_hdmi,sensor_cleaning,ml_shutdown_requested,menu_shown;
struct vram_info vram_lv={0,720,1440,480};
#ifndef FX_MIRROR_UI_HOST_TEST
int FX(active);
#endif
unsigned allocations,commits,preview_test_clock=3000;
unsigned cli(void){return 0;}
void sei(unsigned s){(void)s;}
unsigned get_ms_clock(void){return preview_test_clock;}
int preview_test_half;
int get_halfshutter_pressed(void){return preview_test_half;}
int gui_menu_shown(void){return menu_shown;}
void sync_caches(void){}
struct vram_info *get_yuv422_vram(void){return &vram_lv;}
int module_get_next_loaded(int i){(void)i;return -1;}
const char *module_get_name(int i){(void)i;return 0;}
struct config_var *module_get_config_var(const char*n){(void)n;return 0;}
int module_display_filter_enabled(void){return 0;}
int GetFreeMemForAllocateMemory(void){return 16*1024*1024;}
int GetSizeOfMaxRegion(int *size){*size=16*1024*1024;return 0;}
void *__priv_alloc_dma_memory(size_t n){void*p=malloc(n);if(p)allocations++;return p;}
void __priv_free_dma_memory(void*p){if(p)allocations--;free(p);}
void zoom_overlay_disable(void){}
int should_draw_zoom_overlay(void){return 0;}
int zebra_should_run(void){return 1;}
#ifndef FX_MIRROR_UI_HOST_TEST
int FIO_GetFileSize(const char*p,uint32_t*s){(void)p;(void)s;assert(!"unexpected file access");return -1;}
int is_dir(const char*p){(void)p;assert(!"unexpected file access");return 0;}
int FIO_CreateDirectory(const char*p){(void)p;assert(!"unexpected file access");return -1;}
FILE *FIO_CreateFile(const char*p){(void)p;assert(!"unexpected file write");return 0;}
int FIO_WriteFile(FILE*f,const void*p,size_t n){(void)f;(void)p;(void)n;assert(!"unexpected file write");return -1;}
void FIO_CloseFile(FILE*f){(void)f;assert(!"unexpected file write");}
int FIO_RemoveFile(const char*p){(void)p;assert(!"unexpected file write");return -1;}
#endif
void (*preview_test_commit_hook)(void);
void fx_test_committed_canvas(void){commits++;if(preview_test_commit_hook)preview_test_commit_hook();}
