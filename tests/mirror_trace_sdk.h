#ifndef MIRROR_TRACE_SDK_H
#define MIRROR_TRACE_SDK_H
#include <stdint.h>
extern int lv,lv_paused,gui_state,ml_shutdown_requested;
extern struct test_lens {unsigned job_state;} lens_info;
unsigned cli(void);
void sei(unsigned);
unsigned get_ms_clock(void);
unsigned get_us_clock(void);
void msleep(unsigned);
int get_current_task_id(void);
int get_halfshutter_pressed(void);
int gui_menu_shown(void);
uint32_t read_value(uint8_t *address,int instruction);
int patch_hook_function(uintptr_t address,uint32_t instruction,void (*callback)(uint32_t*,uint32_t*,uint32_t),const char *description);
uint32_t mirror_trace_test_read32(uint32_t address);
uint16_t mirror_trace_test_read16(uint32_t address);
void *mirror_trace_test_sensor_pointer(uint32_t address);
#endif
