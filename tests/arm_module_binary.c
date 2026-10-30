/* SPDX-License-Identifier: GPL-2.0-or-later
 * Synthetic SDK on an ARM board, linked to the existing .mo without recompiling
 * its source. No Canon firmware, loader, physical keys or sensor DMA is tested.
 */
#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <setjmp.h>
#include <module.h>
#include <dryos.h>
#include <menu.h>
#include <config.h>
#include <lens.h>
#include "fx_camera.h"
#include "mirror_camera.h"
#include "mirror_capture_gate.h"
#include "mirror_settings.h"
#undef malloc
#undef free

#define CHECK(x) do {if(!(x)){printf("BINARY FIXTURE FAIL line %u: %s\n",__LINE__,#x);exit(1);}} while(0)
extern module_info_t __module_info_mirror;
extern module_cbr_t __module_cbr_mirror[];
extern module_prophandler_t *__module_prophandlers_mirror[];
extern int mirror_active;
static const char *model,*firmware;
static unsigned clock_ms,allocations,guard_reads,patches,forbidden_native,menu_count,removed,writes;
static void (*pending_worker)(void*);
static struct menu_entry *entry;
static int stepping;
static jmp_buf step_end;
int lv=1,lv_paused,lv_dispsize=1,ext_monitor_hdmi,sensor_cleaning,ml_shutdown_requested,gui_state;
struct lens_info lens_info;
struct vram_info vram_lv;
static struct {unsigned size;unsigned char data[32];} files[2];

int is_camera(const char*m,const char*f){return !strcmp(model,m)&&!strcmp(firmware,f);}
int get_ms_clock(void){return (int)clock_ms;}
uint64_t get_us_clock(void){return (uint64_t)clock_ms*1000;}
bool get_halfshutter_pressed(void){return 0;}
int gui_menu_shown(void){return 0;}
int module_display_filter_enabled(void){return 0;}
int module_get_next_loaded(int i){(void)i;return -1;}
const char *module_get_name(int i){(void)i;return NULL;}
struct config_var *module_get_config_var(const char*n){(void)n;return NULL;}
int zebra_should_run(void){return 1;}
int should_draw_zoom_overlay(void){return 0;}
void zoom_overlay_disable(void){}
#if MODULE_MAJOR >= 8
void sync_caches(void){}
#else
int menu_snprintf(char*p,int n,const char*fmt,...)
{va_list args;va_start(args,fmt);int result=vsnprintf(p,(size_t)n,fmt,args);va_end(args);return result;}
#endif
struct vram_info *get_yuv422_vram(void){return &vram_lv;}
int GetFreeMemForAllocateMemory(void){return 16*1024*1024;}
int GetSizeOfMaxRegion(int *n){*n=16*1024*1024;return 0;}
void *__priv_alloc_dma_memory(size_t n){void*p=malloc(n);if(p)allocations++;return p;}
void __priv_free_dma_memory(void*p){if(p){CHECK(allocations);allocations--;free(p);}}
char *get_config_dir(void){return "ML/SETTINGS/";}
static unsigned slot(const char*p)
{CHECK(!strcmp(p,"ML/SETTINGS/mirror0.prf")||!strcmp(p,"ML/SETTINGS/mirror1.prf"));return p[strlen("ML/SETTINGS/mirror")]-'0';}
int FIO_GetFileSize(const char*p,uint32_t*n){unsigned i=slot(p);*n=files[i].size;return *n?0:-1;}
FILE *FIO_OpenFile(const char*p,unsigned f){(void)f;unsigned i=slot(p);return files[i].size?(FILE*)&files[i]:NULL;}
FILE *FIO_CreateFile(const char*p){unsigned i=slot(p);files[i].size=0;return (FILE*)&files[i];}
static unsigned handle(FILE*f){CHECK(f==(FILE*)&files[0]||f==(FILE*)&files[1]);return f==(FILE*)&files[0]?0:1;}
int FIO_ReadFile(FILE*f,void*p,size_t n){CHECK(n==32);memcpy(p,files[handle(f)].data,n);return (int)n;}
int FIO_WriteFile(FILE*f,const void*p,size_t n){CHECK(n==32);unsigned i=handle(f);memcpy(files[i].data,p,n);files[i].size=n;writes++;return (int)n;}
void FIO_CloseFile(FILE*f){(void)handle(f);}
int FIO_RemoveFile(const char*p){files[slot(p)].size=0;return 0;}
int is_dir(const char*p){(void)p;CHECK(0);return 0;}
int FIO_CreateDirectory(const char*p){(void)p;CHECK(0);return -1;}
#if MODULE_MAJOR >= 8
typedef uint32_t fixture_task;
#else
typedef struct task* fixture_task;
#endif
fixture_task task_create(const char*n,uint32_t p,uint32_t s,void*fn,void*arg)
{CHECK(!strcmp(n,"mirror_worker")&&p==0x1e&&s==0x4000&&!arg);pending_worker=fn;return (fixture_task)0x1234;}
void msleep(int ms)
{
    clock_ms+=(unsigned)ms;
    if(stepping)longjmp(step_end,1);
    if(pending_worker){pending_worker(NULL);pending_worker=NULL;}
}
void menu_add(const char*n,struct menu_entry*p,int count)
{CHECK(!strcmp(n,"Shoot")&&count==1&&!strcmp(p->name,"Mirror Worlds"));entry=p;menu_count++;}
void menu_remove(const char*n,struct menu_entry*p,int count)
{CHECK(!strcmp(n,"Shoot")&&count==1&&p==entry);removed++;}
/* The synthetic core accepts known hook guards but installs no CPU hooks.
 * Every sensor/task/DMA read remains forbidden: no capture stage is simulated. */
uint32_t read_value(uint8_t*p,int instruction)
{
    const mirror_native_backend*b=mirror_camera_native();CHECK(b&&instruction);guard_reads++;
    for(unsigned i=0;i<b->point_count;i++)for(unsigned j=0;j<4;j++)if((uintptr_t)p==b->points[i].pc+j*4)return b->points[i].words[j];
    for(unsigned j=0;j<4;j++)if((uintptr_t)p==b->stage_pc+j*4)return b->stage_words[j];
    CHECK(0);return 0;
}
int patch_hook_function(uintptr_t a,uint32_t word,void*fn,const char*text)
{CHECK(mirror_camera_native()&&a&&word&&fn&&text);patches++;return 0;}
int get_current_task_id(void){forbidden_native++;CHECK(0);return 0;}
uint32_t shamem_read(uint32_t a){(void)a;forbidden_native++;CHECK(0);return 0;}
uint32_t edmac_get_base(uint32_t a){(void)a;forbidden_native++;CHECK(0);return 0;}
uint32_t edmac_get_flags(uint32_t a){(void)a;forbidden_native++;CHECK(0);return 0;}
uint32_t edmac_get_state(uint32_t a){(void)a;forbidden_native++;CHECK(0);return 0;}
uint32_t edmac_get_address(uint32_t a){(void)a;forbidden_native++;CHECK(0);return 0;}
uint32_t edmac_get_pointer(uint32_t a){(void)a;forbidden_native++;CHECK(0);return 0;}

static void pump(void)
{
    CHECK(pending_worker);
    if(!setjmp(step_end)){stepping=1;pending_worker(NULL);}
    stepping=0;
}
static unsigned callback(unsigned type,unsigned value)
{
    for(module_cbr_t*c=__module_cbr_mirror;c->name;c++)if(c->type==type)return c->handler(value);
    CHECK(0);return 0;
}
static void property(unsigned id,uint32_t value)
{
    for(module_prophandler_t**p=__module_prophandlers_mirror;*p;p++)if((*p)->property==id){(*p)->handler(id,NULL,&value,4);return;}
    CHECK(0);
}
static void status(const char*expected)
{
    char value[128]={0},help[256]={0};struct menu_display_info info={0};
    info.value=value;info.help=help;entry->selected=1;entry->update(entry,&info);
    if(strcmp(value,expected))printf("Status mismatch on %s: got '%s', wanted '%s'\n",model,value,expected);
    CHECK(!strcmp(value,expected));
}
static unsigned char source_byte(size_t i){return (unsigned char)((i*37)^(i>>7));}
static void render(void)
{
    size_t n=(size_t)vram_lv.pitch*vram_lv.height;
    unsigned char*src=malloc(n+64),*dst=malloc(n+64);CHECK(src&&dst);
    memset(src,0xcd,n+64);memset(dst,0xa5,n+64);
    for(size_t i=0;i<n;i++)src[i+32]=source_byte(i);
    struct display_filter_buffers buffers={src+32,dst+32};
    CHECK(callback(CBR_DISPLAY_FILTER,0));callback(CBR_DISPLAY_FILTER,(uintptr_t)&buffers);
#ifdef BINARY_CORRUPT_OUTPUT
    dst[32+123]^=1; /* Deliberate oracle self-check; never changes the .mo. */
#endif
    fx_state delivered;CHECK(fx_delivered_state(&delivered));
    CHECK(delivered.params.value[0]==180&&delivered.params.value[1]==2&&delivered.params.value[2]==2);
    for(unsigned y=0;y<(unsigned)vram_lv.height;y++)for(unsigned x=0;x<1440;x++){
        unsigned pair=x/4,original=pair<180?pair:359-pair;
        unsigned component=x%4;
        if(pair!=original&&(component&1))component^=2; /* Reverse the two luma samples, preserve U/V. */
        CHECK(dst[32+y*1440+x]==source_byte(y*1440+original*4+component));
        CHECK(src[32+y*1440+x]==source_byte(y*1440+x));
    }
    for(unsigned i=0;i<32;i++)CHECK(src[i]==0xcd&&src[n+32+i]==0xcd&&dst[i]==0xa5&&dst[n+32+i]==0xa5);
    property(PROP_GUI_STATE,3);CHECK(!callback(CBR_DISPLAY_FILTER,0)&&!fx_delivered_state(&delivered));
    property(PROP_GUI_STATE,0);CHECK(!fx_delivered_state(&delivered));
    callback(CBR_DISPLAY_FILTER,(uintptr_t)&buffers);CHECK(fx_delivered_state(&delivered));
    free(src);free(dst);
}
int main(void)
{
    CHECK(__module_info_mirror.api_magic==0x5a&&__module_info_mirror.api_major==MODULE_MAJOR);
    const char*profiles[][2]={{"EOSM","2.0.2"},{"5D2","2.1.2"},{"5D3","1.1.3"},{"5D3","1.2.3"},
        {"6D","1.1.6"},{"7D","2.0.3"},{"50D","1.0.9"},{"60D","1.1.1"},{"70D","1.1.2"},
        {"100D","1.0.1"},{"550D","1.0.9"},{"600D","1.0.2"},{"650D","1.0.4"},{"700D","1.1.5"},{"1100D","1.0.5"}};
    for(unsigned i=0;i<sizeof(profiles)/sizeof(*profiles);i++){
        model=profiles[i][0];firmware=profiles[i][1];clock_ms=100;
        lv=1;lv_paused=ml_shutdown_requested=0;gui_state=3;lens_info.job_state=0;
        vram_lv=(struct vram_info){NULL,720,1440,!strcmp(model,"1100D")?240:480};
        memset(files,0,sizeof(files));menu_count=removed=guard_reads=patches=0;
        mirror_settings defaults={0,1,0,0};CHECK(mirror_settings_save(&defaults));writes=0;
        CHECK(!__module_info_mirror.init()&&menu_count==1&&!mirror_active&&!allocations);status("OFF");
        CHECK(!strcmp(mirror_camera_name(),model));
        int native=mirror_camera_native()!=NULL;
        CHECK(native==(MODULE_MAJOR==8&&!strcmp(model,"EOSM")));
        entry->select(entry->priv,1);clock_ms=1700;pump();CHECK(mirror_active&&allocations);status("ON - Preparing");
        CHECK(!callback(CBR_DISPLAY_FILTER,0)); /* init must seed existing Canon review state. */
        gui_state=0;property(PROP_GUI_STATE,0);
        render();if(native)pump();status(native?"ON - Ready":"ON - Preview only");
        CHECK(callback(CBR_KEYPRESS,MODULE_KEY_PRESS_SET)==1&&callback(CBR_KEYPRESS,MODULE_KEY_PLAY)==1);
        entry->select(entry->priv,1);clock_ms+=500;pump();CHECK(!mirror_active&&!allocations);status("OFF");
        entry->select(entry->priv,1);pump();CHECK(mirror_active&&allocations);status("ON - Preparing");
        render();
        CHECK(!__module_info_mirror.deinit()&&removed==1&&!mirror_active&&!allocations&&writes);
        if(!native)CHECK(!guard_reads&&!patches);
        CHECK(!forbidden_native);
        printf("BINARY_PROFILE %s %s %u %u PASS\n",model,firmware,MODULE_MAJOR,vram_lv.height);
    }
    model="EOSM";firmware="0.0.0";menu_count=0;
    CHECK(__module_info_mirror.init()==1&&!menu_count&&!allocations);
    printf("BINARY_MODULE_RESULT api=%u profiles=15 unsupported=1 sensor_reads=0 PASS\n",MODULE_MAJOR);
    return 0;
}
