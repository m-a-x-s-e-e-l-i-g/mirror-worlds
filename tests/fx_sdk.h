#ifndef FX_SDK_H
#define FX_SDK_H
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#define CACHEABLE(p) (p)
#define MODULE_KEY_PRESS_HALFSHUTTER 1
#define MODULE_KEY_PRESS_FULLSHUTTER 3
#define MODULE_KEY_WHEEL_LEFT 7
#define MODULE_KEY_WHEEL_RIGHT 8
#define MODULE_KEY_PRESS_SET 9
#define MODULE_KEY_UNPRESS_SET 10
#define MODULE_KEY_PRESS_UP 12
#define MODULE_KEY_PRESS_RIGHT 15
#define MODULE_KEY_PRESS_LEFT 16
#define MODULE_KEY_PRESS_DOWN 19
#define MODULE_KEY_UNPRESS_UDLR 20
#define MODULE_KEY_MENU 22
#define MODULE_KEY_PLAY 24
extern int lv,lv_paused,lv_dispsize,ext_monitor_hdmi,sensor_cleaning,ml_shutdown_requested;
struct vram_info {uint8_t *vram;int width,pitch,height;};
struct display_filter_buffers {void *src_buf,*dst_buf;};
extern struct vram_info vram_lv;
struct config_var {int *value;};
unsigned cli(void);
void sei(unsigned);
unsigned get_ms_clock(void);
int get_halfshutter_pressed(void);
int gui_menu_shown(void);
void sync_caches(void);
struct vram_info *get_yuv422_vram(void);
int module_get_next_loaded(int);
const char *module_get_name(int);
struct config_var *module_get_config_var(const char*);
int module_display_filter_enabled(void);
int FIO_GetFileSize(const char*,uint32_t*);
int is_dir(const char*);
int FIO_CreateDirectory(const char*);
FILE *FIO_CreateFile(const char*);
int FIO_WriteFile(FILE*,const void*,size_t);
void FIO_CloseFile(FILE*);
int FIO_RemoveFile(const char*);
void fx_test_committed_canvas(void);
#endif
