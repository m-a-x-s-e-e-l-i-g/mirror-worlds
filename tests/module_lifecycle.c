/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include "mirror_ui_sdk.h"
#include "mirror_settings_sdk.h"
#include "../modules/mirror/mirror.c"
extern unsigned allocations,preview_test_clock;
int gui_state;struct test_lens lens_info;
static const char *model="700D",*firmware="1.1.5";
static struct {unsigned size;unsigned char bytes[32];} files[2];
static unsigned writes,fail_write,menu_count,removed,task_failure,worker_running;
static void (*pending_worker)(void*);
int is_camera(const char*m,const char*f){return !strcmp(model,m)&&!strcmp(firmware,f);}
const char *get_config_dir(void){return "ML/SETTINGS/";}
static unsigned file_index(const char*p)
{
    assert(!strcmp(p,"ML/SETTINGS/mirror0.prf")||!strcmp(p,"ML/SETTINGS/mirror1.prf"));
    return p[strlen("ML/SETTINGS/mirror")]-'0';
}
int FIO_GetFileSize(const char*p,uint32_t*size){unsigned i=file_index(p);*size=files[i].size;return *size?0:-1;}
FILE *FIO_OpenFile(const char*p,unsigned flags){(void)flags;unsigned i=file_index(p);return files[i].size?(FILE*)&files[i]:0;}
FILE *FIO_CreateFile(const char*p){unsigned i=file_index(p);files[i].size=0;return (FILE*)&files[i];}
int FIO_ReadFile(FILE*f,void*out,size_t bytes)
{unsigned i=f==(FILE*)&files[0]?0:1;assert(f==(FILE*)&files[i]&&bytes<=32);memcpy(out,files[i].bytes,bytes);return (int)bytes;}
int FIO_WriteFile(FILE*f,const void*data,size_t bytes)
{
    unsigned i=f==(FILE*)&files[0]?0:1;assert(f==(FILE*)&files[i]&&bytes==32);writes++;
    if(fail_write)return -1;
    memcpy(files[i].bytes,data,bytes);files[i].size=(unsigned)bytes;return (int)bytes;
}
void FIO_CloseFile(FILE*f){assert(f==(FILE*)&files[0]||f==(FILE*)&files[1]);}
int FIO_RemoveFile(const char*p){files[file_index(p)].size=0;return 0;}
int is_dir(const char*p){(void)p;assert(0);return 0;}
int FIO_CreateDirectory(const char*p){(void)p;assert(0);return -1;}
uintptr_t task_create(const char*name,unsigned priority,unsigned stack,void(*fn)(void*),void*arg)
{
    assert(!strcmp(name,"mirror_worker")&&priority==0x1e&&stack==0x4000&&!arg);
    if(task_failure)return task_failure==1?0:0xffffffffu;
    pending_worker=fn;return 0x1234;
}
void menu_add(const char*tab,struct menu_entry*items,unsigned count)
{assert(!strcmp(tab,"Shoot")&&items==entries&&count==1);menu_count++;}
void menu_remove(const char*tab,struct menu_entry*items,unsigned count)
{assert(!strcmp(tab,"Shoot")&&items==entries&&count==1);removed++;}
void msleep(unsigned ms)
{
    preview_test_clock+=ms;
    if(shutting_down&&pending_worker&&!worker_running){worker_running=1;pending_worker(0);pending_worker=0;worker_running=0;}
}
static void begin(unsigned state,unsigned enabled)
{
    assert(!allocations);memset(files,0,sizeof(files));
    mirror_settings stored={enabled,1,0,0};mirror_settings_load(&stored);assert(mirror_settings_save(&stored));
    gui_state=(int)state;lv=1;lv_paused=ml_shutdown_requested=0;lens_info.job_state=0;
    vram_lv.width=720;vram_lv.pitch=1440;vram_lv.height=!strcmp(model,"1100D")?240:480;
    preview_test_clock=100;writes=removed=menu_count=task_failure=0;
    pending_worker=0;preferences=(mirror_settings){0,1,0,0};
    assert(!init());assert(menu_count==1&&!mirror_active);
}
static void initial_review(unsigned state)
{
    begin(state,1);service_once();assert(!mirror_active&&!allocations);
    preview_test_clock=1600;service_once();
    assert(mirror_active&&allocations);
    if(state==1||state==3||state==12)assert(!fx_filter(0));
    else assert(fx_filter(0));
    assert(!deinit()&&removed==1&&!allocations&&!mirror_active);
}
static void status_value(const char*expected)
{
    char value[128]={0},help[512]={0};struct menu_display_info info={value,help};
    entries[0].selected=1;status(&entries[0],&info);assert(!strcmp(value,expected));
    assert(strstr(help,"photos stay original"));
}
static void start_status(void)
{
    begin(0,1);preview_test_clock=1600;service_once();
    status_value("ON - Preparing");
    assert(!deinit()&&removed==1&&!allocations);
}
static void controls_and_persistence(void)
{
    begin(0,0);preview_test_clock=1600;service_once();assert(!mirror_active&&!allocations);status_value("OFF");
    entries[0].select(entries[0].priv,1);service_once();assert(mirror_active&&allocations);status_value("ON - Preparing");
    size_t bytes=(size_t)vram_lv.pitch*vram_lv.height;unsigned char *src=malloc(bytes),*dst=malloc(bytes);
    assert(src&&dst);memset(src,0x43,bytes);memset(dst,0xa5,bytes);
    struct display_filter_buffers buffers={src,dst};assert(fx_filter(0));fx_filter(&buffers);
    fx_state state;assert(fx_delivered_state(&state));status_value("ON - Preview only");
    /* The actual module property entry point must invalidate old delivery. */
    unsigned review=3;ui_property_PROP_GUI_STATE(&review,4);memset(dst,0xa5,bytes);
    assert(!fx_filter(0));fx_filter(&buffers);assert(!fx_delivered_state(&state));
    for(size_t i=0;i<bytes;i++)assert(dst[i]==0xa5);
    review=0;ui_property_PROP_GUI_STATE(&review,4);assert(!fx_delivered_state(&state));
    fx_filter(&buffers);assert(fx_delivered_state(&state));
    /* An earlier session's cumulative frame count cannot make a new ON ready. */
    entries[0].select(entries[0].priv,1);service_once();assert(!mirror_active&&!allocations);status_value("OFF");
    entries[0].select(entries[0].priv,1);service_once();assert(mirror_active&&allocations);status_value("ON - Preparing");
    fx_filter(&buffers);assert(fx_delivered_state(&state));status_value("ON - Preview only");
    assert(key(MODULE_KEY_PRESS_FULLSHUTTER)==1&&key(MODULE_KEY_PRESS_SET)==1&&key(MODULE_KEY_PLAY)==1);
    /* Every valid UI choice must generate a valid portable preference record. */
    for(unsigned p=0;p<7;p++){
        configure(&preferences.placement,1);assert(mirror_settings_valid(&preferences));
        for(unsigned n=0;n<6;n++){
            configure(&preferences.width,1);configure(&preferences.height,-1);
            assert(mirror_settings_valid(&preferences));
        }
    }
    unsigned before=writes;preview_test_clock+=399;service_once();assert(writes==before);
    fail_write=1;preview_test_clock++;service_once();assert(save_error&&dirty&&writes==before+1);
    fail_write=0;preview_test_clock+=1999;service_once();assert(writes==before+1);
    preview_test_clock++;service_once();assert(!save_error&&!dirty&&writes==before+2);
    mirror_settings saved={0};assert(mirror_settings_load(&saved)&&!memcmp(&saved,&preferences,sizeof(saved)));
    /* Shutdown persists desired ON even though the renderer must stop. */
    configure(&preferences.placement,-1);assert(dirty&&preferences.enabled);
    assert(!deinit()&&!mirror_active&&!allocations&&removed==1);
    assert(mirror_settings_load(&saved)&&saved.enabled==1&&!memcmp(&saved,&preferences,sizeof(saved)));
    free(src);free(dst);
}
int main(int argc,char**argv)
{
    if(argc>1&&!strcmp(argv[1],"status")){start_status();return 0;}
    const char*profiles[][2]={{"EOSM","2.0.2"},{"5D2","2.1.2"},{"5D3","1.1.3"},{"5D3","1.2.3"},
        {"6D","1.1.6"},{"7D","2.0.3"},{"50D","1.0.9"},{"60D","1.1.1"},{"70D","1.1.2"},
        {"100D","1.0.1"},{"550D","1.0.9"},{"600D","1.0.2"},{"650D","1.0.4"},{"700D","1.1.5"},{"1100D","1.0.5"}};
    for(unsigned i=0;i<sizeof(profiles)/sizeof(*profiles);i++){
        model=profiles[i][0];firmware=profiles[i][1];
        initial_review(0);initial_review(1);initial_review(3);initial_review(12);
        start_status();controls_and_persistence();
    }
    menu_count=writes=0;model="EOSM";firmware="0.0.0";
    assert(init()==1&&!menu_count&&!writes&&!allocations&&!mirror_active);
    firmware="2.0.2";
    for(task_failure=1;task_failure<=2;task_failure++)
        assert(init()==1&&!menu_count&&!allocations&&!mirror_active&&!pending_worker);
    puts("Module lifecycle: 15 profiles, initial review states, first frame, controls, save retry and shutdown persistence: PASS");
    return 0;
}
