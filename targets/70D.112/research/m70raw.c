/* Unshipped virtual-camera experiment. Arm only with the QEMU-checked GDB tool.
 * No camera backend selection, auto-arm, flash writes or pixel IO from worker.
 * The hooked task uses the actual Mirror Canon14 transform, not debugger writes.
 */
#ifndef M70_EMULATOR_RESEARCH
#error This module is only built by the isolated 70D emulator research builder
#endif
#include <module.h>
#include <dryos.h>
#include <config.h>
#include <lens.h>
#include <patch.h>
#include <tasks.h>
#include <vram.h>
#include <string.h>
#include "fx_mirror_sensor.h"
#include "fx_mirror_edges.h"
#include "raw_contract.h"
#include "rom_guards.h"

CONFIG_INT("m70raw.arm",m70_arm,0);
CONFIG_INT("m70raw.mode",m70_mode,1); /* 1 read-only hold, 2 mirror */
CONFIG_INT("m70raw.edges",m70_edges,2);
CONFIG_INT("m70raw.width",m70_width,2);
CONFIG_INT("m70raw.height",m70_height,2);
CONFIG_INT("m70raw.report",m70_report_address,0);
typedef struct {
    uint32_t phase,error,installed,overlaps,first_overlap,consumer_events;
    uint32_t before_hash,after_hash,hold_us,transform_us,changed,mode,task;
    uint32_t consumer_pc[16],consumer_source[16];
    fx_params params;
    m70_binding binding;
} m70_report;
/* Public debugger symbol for this unshipped probe; no Canon structure ABI. */
static m70_report report;
static fx_mirror_raw map;
static unsigned held,armed,closed,pending,finished;
static m70_binding snapshot(uint32_t *regs)
{
    extern uint32_t edmac_get_state(uint32_t),edmac_get_flags(uint32_t),edmac_get_address(uint32_t),edmac_get_pointer(uint32_t);
    unsigned a=shamem_read(0xc0f04014),b=shamem_read(0xc0f04010),n=shamem_read(0xc0f0400c);
    m70_binding s={.source=regs[0],.job=*(volatile uint32_t*)0x7c208,.context=regs[10],.caller=regs[13],.cpsr=regs[-1],
        .liveview=lv,.job_state=lens_info.job_state,.shutdown=ml_shutdown_requested,
        .state_before=edmac_get_state(0),.flags=edmac_get_flags(0),.address=edmac_get_address(0),.pointer=edmac_get_pointer(0),
        .xa=a&65535,.ya=a>>16,.xb=b&65535,.yb=b>>16,.xn=n&65535,.yn=n>>16,
        .off1a=shamem_read(0xc0f04020),.off1b=shamem_read(0xc0f04018),
        .off2a=shamem_read(0xc0f04024),.off2b=shamem_read(0xc0f0401c),.off3=shamem_read(0xc0f04028)};
    s.state_after=edmac_get_state(0);return s;
}
static uint32_t samples(uint32_t source)
{
    uint32_t hash=2166136261u;
    const volatile uint16_t *base=(const volatile uint16_t*)((m70_canonical(source)+M70_PITCH)|0x40000000u);
    for(unsigned y=0;y<8;y++)for(unsigned x=0;x<8;x++){
        unsigned row=(y*(M70_HEIGHT-2)/7)&~1u,col=(x*((M70_WIDTH-8)/8)/7)*8;
        const volatile uint16_t *p=base+row*(M70_PITCH/2)+col*7/8;
        for(unsigned i=0;i<7;i++){hash^=p[i];hash*=16777619u;}
    }
    return hash;
}
static void consumer(uint32_t *regs,uint32_t *stack,uint32_t pc)
{
    if(closed||!regs||stack!=regs+14)return;
    if(held){report.overlaps++;if(!report.first_overlap)report.first_overlap=pc;}
    if(report.phase>=2&&report.consumer_events<16){
        unsigned i=report.consumer_events++;
        report.consumer_pc[i]=pc;
        report.consumer_source[i]=pc==0xff437d58?*(volatile uint32_t*)(0xc1770+0x58):regs[0];
    }
}
static void stage(uint32_t *regs,uint32_t *stack,uint32_t pc)
{
    if(!armed||closed)return;
    armed=0;report.phase=2;
    if(!regs||stack!=regs+14||pc!=0xff361910){report.error=1;goto done;}
    report.binding=snapshot(regs);report.task=get_current_task_id();
    if(!m70_binding_valid(&report.binding)){report.error=2;goto done;}
    report.before_hash=samples(report.binding.source);
    held=1;unsigned began=get_us_clock();
    for(unsigned i=0;i<20&&!closed&&!ml_shutdown_requested&&!report.overlaps;i++)msleep(5);
    report.hold_us=get_us_clock()-began;
    m70_binding after=snapshot(regs);
    report.after_hash=samples(report.binding.source);
    if(closed||ml_shutdown_requested||report.overlaps||!m70_binding_valid(&after)||
        memcmp(&after,&report.binding,sizeof(after))||report.after_hash!=report.before_hash){report.error=3;goto release;}
    if(report.mode==2){
        void *pixels=(void*)((m70_canonical(report.binding.source)+M70_PITCH)|0x40000000u);
        gl_frame frame={pixels,M70_BYTES,M70_WIDTH,M70_HEIGHT,M70_PITCH,GL_CANON14,0,16383};
        if(fx_mirror_raw_prepare(&map,&frame,m70_region,&report.params,0)){report.error=4;goto release;}
        began=get_us_clock();
        int result=fx_mirror_sensor_axial(&map,pixels,M70_BYTES);
        unsigned zero=0;__asm__ __volatile__("mcr p15, 0, %0, c7, c10, 4"::"r"(zero):"memory");
        report.transform_us=get_us_clock()-began;
        if(result)report.error=5;else report.changed=1;
    }
release:
    held=0;
done:
    report.phase=report.error?4:3;pending=1;
}
static int install(void)
{
    for(unsigned i=0;i<M70_GUARDS;i++)for(unsigned j=0;j<4;j++)
        if(read_value((uint8_t*)(m70_guards[i].pc+j*4),1)!=m70_guards[i].words[j])return 1;
    for(unsigned i=0;i<M70_GUARDS;i++)for(unsigned j=0;j<i;j++)
        if((m70_guards[i].pc&0x7e0)==(m70_guards[j].pc&0x7e0)&&
            (m70_guards[i].pc&~31u)!=(m70_guards[j].pc&~31u))return 2;
    for(unsigned i=0;i<M70_GUARDS;i++){
        if(patch_hook_function(m70_guards[i].pc,m70_guards[i].words[0],i?consumer:stage,"70D QEMU RAW research"))return 3;
        report.installed|=1u<<i;
    }
    return 0;
}
static void worker(void *unused)
{
    (void)unused;
    while(!closed){
        if(m70_arm==0x51454d55){
            m70_arm=0;
            if(!armed&&!held&&!lens_info.job_state&&!ml_shutdown_requested){
                unsigned installed=report.installed;memset(&report,0,sizeof(report));report.installed=installed;
                report.mode=m70_mode;report.params=(fx_params){{FX_MIRROR_EDGES,m70_edges,m70_width,m70_height}};
                if((report.mode!=1&&report.mode!=2)||!fx_edges_valid(&report.params))report.error=6;
                else if(report.installed&&report.installed!=((1u<<M70_GUARDS)-1))report.error=7;
                else if(!report.installed)report.error=install();
                report.phase=report.error?4:1;armed=!report.error;
                DryosDebugMsg(0,15,"M70RAW armed=%u error=%u hooks=%x mode=%u",armed,report.error,report.installed,report.mode);
            }
        }
        if(pending){pending=0;DryosDebugMsg(0,15,"M70RAW phase=%u error=%u hold=%u transform=%u overlaps=%u changed=%u",
            report.phase,report.error,report.hold_us,report.transform_us,report.overlaps,report.changed);}
        msleep(20);
    }
    finished=1;
}
static unsigned init(void)
{
    if(!is_camera("70D","1.1.2"))return 1;
    closed=finished=held=armed=pending=0;m70_arm=0;memset(&report,0,sizeof(report));
    m70_report_address=(unsigned)&report;
    unsigned task=task_create("m70raw_probe",0x1e,0x4000,worker,0);
    return !task||task==0xffffffff;
}
static unsigned deinit(void)
{
    closed=1;armed=0;for(unsigned i=0;i<100&&!finished;i++)msleep(10);
    return !finished||held;
}
MODULE_INFO_START() MODULE_LONGNAME("70D QEMU RAW research - not a camera build") MODULE_INIT(init) MODULE_DEINIT(deinit) MODULE_INFO_END()
MODULE_CBRS_START() MODULE_CBRS_END()
MODULE_PROPHANDLERS_START() MODULE_PROPHANDLERS_END()
MODULE_CONFIGS_START() MODULE_CONFIG(m70_arm) MODULE_CONFIG(m70_mode) MODULE_CONFIG(m70_edges) MODULE_CONFIG(m70_width) MODULE_CONFIG(m70_height) MODULE_CONFIG(m70_report_address) MODULE_CONFIGS_END()
