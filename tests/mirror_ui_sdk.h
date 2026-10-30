#ifndef MIRROR_UI_SDK_H
#define MIRROR_UI_SDK_H
#include <stdio.h>
#include <stdint.h>
#include "fx_sdk.h"
#include "mirror_trace_sdk.h"
#define CONFIG_INT(name,variable,value) int variable=value
#define COUNT(a) (sizeof(a)/sizeof((a)[0]))
#define MENU_SELECT_FUNC(name) void name(void*priv,int delta)
#define MENU_UPDATE_FUNC(name) void name(struct menu_entry*entry,struct menu_display_info*info)
struct menu_display_info {char *value,*help;};
struct menu_entry {
    const char *name;void *priv;int max;
    void (*select)(void*,int);
    void (*update)(struct menu_entry*,struct menu_display_info*);
    struct menu_entry *children;const char **choices;const char *help;unsigned selected;
};
#define MENU_SET_VALUE(...) snprintf(info->value,128,__VA_ARGS__)
#define MENU_SET_HELP(...) do{if(entry->selected)snprintf(info->help,512,__VA_ARGS__);}while(0)
#define MENU_EOL {0}
#define PROP_HANDLER(name) void ui_property_##name(unsigned*buf,unsigned len)
#define MODULE_INFO_START()
#define MODULE_LONGNAME(name)
#define MODULE_INIT(func)
#define MODULE_DEINIT(func)
#define MODULE_INFO_END()
#define MODULE_CBRS_START()
#define MODULE_CBR(type,func,ctx)
#define MODULE_CBRS_END()
#define MODULE_PROPHANDLERS_START()
#define MODULE_PROPHANDLER(name)
#define MODULE_PROPHANDLERS_END()
#define MODULE_CONFIGS_START()
#define MODULE_CONFIG(name)
#define MODULE_CONFIGS_END()
uintptr_t task_create(const char*,unsigned,unsigned,void(*)(void*),void*);
void menu_add(const char*,struct menu_entry*,unsigned);
void menu_remove(const char*,struct menu_entry*,unsigned);
#endif
