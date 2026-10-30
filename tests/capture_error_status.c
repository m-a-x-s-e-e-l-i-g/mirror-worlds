/* SPDX-License-Identifier: GPL-2.0-or-later
 * Exercise the actual menu callback with EOS M's unsupported-%u behavior.
 * Other module functions are discarded by the linker's section collection.
 */
#include <assert.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include "mirror_ui_sdk.h"
#include "fx_camera.h"
#include "mirror_capture_gate.h"
#include "mirror_raw_trace.h"
#include "mirror_camera.h"
static mirror_gate_report failed;
static mirror_raw_trace_report trace_report;
static unsigned unsigned_requests;
static int rom_menu_snprintf(char*out,size_t cap,const char*format,...)
{
    char supported[256];size_t n=0;
    /* In the reported help string the unsupported conversion is the last
     * argument. Reproducing its literal 'u' does not shift a later argument. */
    for(size_t i=0;format[i];i++){
        assert(n+2<sizeof(supported));
        if(format[i]=='%'&&format[i+1]=='u'){supported[n++]='u';i++;unsigned_requests++;}
        else supported[n++]=format[i];
    }
    supported[n]=0;
    va_list ap;va_start(ap,format);int result=vsnprintf(out,cap,supported,ap);va_end(ap);return result;
}
#undef MENU_SET_VALUE
#undef MENU_SET_HELP
#define MENU_SET_VALUE(...) rom_menu_snprintf(info->value,35,__VA_ARGS__)
#define MENU_SET_HELP(...) do{if(entry->selected)rom_menu_snprintf(info->help,100,__VA_ARGS__);}while(0)
#include "../modules/mirror/mirror.c"
void fx_status_get(fx_status*out){memset(out,0,sizeof(*out));}
void mirror_gate_status(mirror_gate_report*out){*out=failed;}
void mirror_raw_trace_status(mirror_raw_trace_report*out){*out=trace_report;}
const mirror_native_backend *mirror_camera_native(void){return NULL;}
const char *mirror_camera_name(void){return "EOSM";}
int main(void)
{
    char value[35],help[100],number[16];struct menu_entry entry={.selected=1};
    struct menu_display_info info={value,help};
    for(unsigned code=1;code<=MG_CONTROLS;code++){
        if(code==MG_CANCEL||code==MG_SHUTDOWN)continue;
        memset(value,0,sizeof(value));memset(help,0,sizeof(help));
        failed=(mirror_gate_report){.phase=MG_FAILED,.error=code,.core_error=12,.first_overlap_pc=0xff123456};
        trace_report=(mirror_raw_trace_report){.phase=MT_FAILED,.error=MT_GUARD,.core_error=12,.error_pc=0xff123456};
        status(&entry,&info);snprintf(number,sizeof(number),"(%u)",code);
        printf("CAPTURE_UI %u: %s | %s\n",code,value,help);
        assert(strstr(value,number));assert(!strstr(help,"code u"));
        assert(strlen(value)<sizeof(value)&&strlen(help)<sizeof(help));
        if(code==MG_TRACE_FAILED)assert(strstr(help,"trace 2")&&strstr(help,"ff123456"));
        if(code==MG_OVERLAP)assert(strstr(help,"ff123456"));
    }
    assert(!unsigned_requests);
    puts("Capture error UI: numeric codes, reasons, trace/overlap details and Canon formatter compatibility: PASS");
    return 0;
}
