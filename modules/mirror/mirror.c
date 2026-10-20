/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifdef FX_MIRROR_UI_HOST_TEST
#include "mirror_ui_sdk.h"
#else
#include <module.h>
#include <dryos.h>
#include <menu.h>
#include <property.h>
#include <config.h>
#include <lens.h>
#endif
#include "fx_camera.h"
#include "effect_config.h"
#include "mirror_raw_trace.h"
#include "mirror_capture_gate.h"
#include "mirror_settings.h"
CONFIG_INT("maxmade.fx.mirror.busy",mirror_active,0);
static volatile int shutting_down,finished;
static mirror_settings preferences={0,1,0,0};
static unsigned attempted,started_ms,dirty,changed_ms,save_error;
static const char*placements[]={"Left","Right","Top","Bottom","Left + Right","Top + Bottom","All edges"};
static const char*sizes[]={"Half","Third","Quarter","Fifth","Sixth"};
static struct menu_entry entries[];
static void service_once(void)
{
    unsigned now=get_ms_clock();
    if(!preferences.enabled||shutting_down||ml_shutdown_requested)fx_stop();
    if(preferences.enabled&&!attempted&&!mirror_active&&!shutting_down&&!ml_shutdown_requested&&
       now-started_ms>=1500&&!lens_info.job_state&&lv&&!lv_paused&&!get_halfshutter_pressed()&&!gui_menu_shown()){
        attempted=1;
        if(fx_start())mirror_gate_automatic(1);
    }
    /* A menu OFF arriving while startup resolves the module family wins. */
    if(!preferences.enabled)fx_stop();
    fx_service();
    if(!mirror_active){mirror_gate_automatic(0);mirror_raw_trace_cancel();}
    mirror_raw_trace_service();mirror_gate_service();
    mirror_gate_report capture;mirror_gate_status(&capture);
    if(mirror_active&&capture.phase==MG_FAILED)fx_stop();
    if(dirty&&!lens_info.job_state&&capture.phase!=MG_HELD&&!get_halfshutter_pressed()&&
       (shutting_down||ml_shutdown_requested||now-changed_ms>=(save_error?2000u:400u))){
        mirror_settings snapshot=preferences;
        if(mirror_settings_save(&snapshot)){
            if(preferences.enabled==snapshot.enabled&&preferences.placement==snapshot.placement&&
               preferences.width==snapshot.width&&preferences.height==snapshot.height)dirty=0;
            save_error=0;
        }else{save_error=1;changed_ms=now;}
    }
}
static void worker(void*unused)
{
    while(!shutting_down||mirror_active){service_once();msleep(20);}
    /* Persist the desired ON/OFF state, never the transient shutdown state. */
    if(dirty)mirror_settings_save(&preferences);
    finished=1;
}
PROP_HANDLER(PROP_HALF_SHUTTER){if(buf&&len)fx_half(((unsigned char*)buf)[0]!=0);}
PROP_HANDLER(PROP_GUI_STATE){if(buf&&len>=4)fx_canon_gui(((unsigned*)buf)[0]);}
static unsigned int filter(unsigned int ctx){return fx_filter((void*)(uintptr_t)ctx);}
static unsigned int key(unsigned int value)
{
    if(value==3u)mirror_gate_full_press();
    return fx_key(value); /* Physical shutter, SET and Play remain Canon controls. */
}
static void settings_changed(void)
{
    unsigned mask=mirror_edge_mask(preferences.placement);
    if((mask&3)==3&&!preferences.width)preferences.width=1;
    if((mask&12)==12&&!preferences.height)preferences.height=1;
    fx_params p=mirror_settings_params(&preferences);fx_controls(&p);
    dirty=1;changed_ms=get_ms_clock();
}
static MENU_SELECT_FUNC(toggle)
{
    preferences.enabled=!preferences.enabled;attempted=0;
    if(!preferences.enabled){mirror_gate_automatic(0);mirror_raw_trace_cancel();fx_stop();}
    settings_changed();
}
static MENU_SELECT_FUNC(configure)
{
    int step=delta<0?-1:1;
    if(priv==&preferences.placement)preferences.placement=(preferences.placement+7+step)%7;
    else{
        unsigned mask=mirror_edge_mask(preferences.placement);
        unsigned*value=priv;
        if((value==&preferences.width&&!(mask&3))||(value==&preferences.height&&!(mask&12)))return;
        unsigned first=(value==&preferences.width?(mask&3)==3:(mask&12)==12)?1:0;
        int next=(int)*value+step;
        if(next<(int)first)next=4;else if(next>4)next=(int)first;
        *value=(unsigned)next;
    }
    settings_changed();
}
static MENU_UPDATE_FUNC(size_status)
{
    unsigned mask=mirror_edge_mask(preferences.placement);
    unsigned*value=entry->priv;int used=value==&preferences.width?(mask&3):(mask&12);
    MENU_SET_VALUE("%s",used?sizes[*value]:"Not used");
    MENU_SET_HELP("Size of each mirrored border. Opposing edges start at Third to keep an original center.");
}
static const char*reason(unsigned code)
{
    switch(code){case 10:return "Not enough memory";case 11:return "Stop other effect";
    case 12:return "Native 1x LCD required";case 13:return "Image processing";
    case 14:return "No display delivery";case 16:return "Cancelled";default:return "Preview unavailable";}
}
static MENU_UPDATE_FUNC(status)
{
    fx_status r;fx_status_get(&r);mirror_gate_report capture;mirror_gate_status(&capture);
    if(capture.phase==MG_FAILED&&capture.error!=MG_CANCEL&&capture.error!=MG_SHUTDOWN){
        MENU_SET_VALUE("Capture unavailable");
        MENU_SET_HELP("%s. Capture stopped (code %u). Switch OFF/ON to retry; restart if it persists.",FX_VERSION,capture.error);
    }else if(r.error){MENU_SET_VALUE("%s",reason(r.error));
        MENU_SET_HELP("%s. A+ / Auto ISO, Canon RAW, native 1x LCD and Global Draw ON.",FX_VERSION);
    }else{
        MENU_SET_VALUE("%s",!r.running?(preferences.enabled?"ON - Preparing":"OFF"):capture.phase==MG_ARMED?"ON - Ready":capture.phase==MG_HELD?"ON - Saving":"ON - Preparing");
        MENU_SET_HELP("%s. %s. Physical shutter saves mirrored CR2; release between shots. Settings remembered.",FX_VERSION,placements[preferences.placement]);
    }
    if(save_error)MENU_SET_HELP("Could not save preferences. Check card write access; settings remain active this session.");
}
static struct menu_entry entries[]={
    {.name="Mirror Worlds",.priv=&preferences.enabled,.max=1,.select=toggle,.update=status,
     .help=FX_VERSION " / Edge reflections in preview and Canon RAW. Remembers last settings.",
     .children=(struct menu_entry[]){
        {.name="Live effect",.priv=&preferences.enabled,.max=1,.select=toggle,.update=status},
        {.name="Mirror on",.priv=&preferences.placement,.max=6,.select=configure,.choices=placements,
         .help="Which areas are replaced by reflections; the remaining source stays original."},
        {.name="Width",.priv=&preferences.width,.max=4,.select=configure,.update=size_status,.choices=sizes},
        {.name="Height",.priv=&preferences.height,.max=4,.select=configure,.update=size_status,.choices=sizes},
        MENU_EOL,
     }},
};
static unsigned int init(void)
{
    if(!is_camera("EOSM","2.0.2"))return 1;
    fx_camera_init();if(!fx_native_capture_mode())return 1;
    mirror_settings_load(&preferences);
    fx_params p=mirror_settings_params(&preferences);fx_controls(&p);
    fx_canon_gui(0);shutting_down=finished=0;attempted=dirty=save_error=0;started_ms=get_ms_clock();
    unsigned task=task_create("mirror_worker",0x1e,0x4000,worker,0);
    if(!task||task==0xffffffff)return 1;
    menu_add("Shoot",entries,COUNT(entries));return 0;
}
static unsigned int deinit(void)
{
    mirror_gate_shutdown();mirror_raw_trace_shutdown();shutting_down=1;fx_stop();
    mirror_gate_report capture;
    for(unsigned i=0;i<600;i++){
        mirror_gate_status(&capture);
        if(finished&&capture.phase!=MG_HELD)break;
        msleep(5);
    }
    mirror_gate_status(&capture);if(!finished||capture.phase==MG_HELD)return 1;
    menu_remove("Shoot",entries,COUNT(entries));return 0;
}
MODULE_INFO_START() MODULE_LONGNAME("Mirror Worlds") MODULE_INIT(init) MODULE_DEINIT(deinit) MODULE_INFO_END()
MODULE_CBRS_START()
    MODULE_CBR(CBR_DISPLAY_FILTER,filter,0)
    MODULE_CBR(CBR_KEYPRESS,key,0)
MODULE_CBRS_END()
MODULE_PROPHANDLERS_START()
    MODULE_PROPHANDLER(PROP_HALF_SHUTTER) MODULE_PROPHANDLER(PROP_GUI_STATE)
MODULE_PROPHANDLERS_END()
MODULE_CONFIGS_START() MODULE_CONFIG(mirror_active) MODULE_CONFIGS_END()
