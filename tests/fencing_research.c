/* Completion-only emulator guard fixture; no Canon data/firmware required. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {uint32_t addr;uint16_t xa,ya,xb,yb,xn,yn;uint32_t off1a,off1b,off2a,off2b,off3,off34,off40,flags;} EDmacChState;
typedef struct {void*buf;uint32_t data_size;} EDmacData;
static struct {int jp57_research;} capture={1};
static struct model {const char*name;unsigned firmware_version,digic_version;typeof(capture)*capture;} model={"70D",112,5,&capture};
static struct state {struct model*model;struct {EDmacChState ch[64];unsigned read_conn[64],write_conn[64];EDmacData conn_data[64];} edmac;} state;
static struct state*eos_state=&state;
static const char*option="1";
static unsigned count,last_irq;
static void eos_trigger_int(unsigned irq,unsigned delay){assert(delay==(irq==0xd0?5u:314u));count++;last_irq=irq;}
#define MODE_WRITE 1
#define getenv(name) option
#include "../targets/70D.112/qemu/fencing_research.inc.c"
#undef getenv
static void setup(void)
{
    if(state.edmac.conn_data[14].buf)free(state.edmac.conn_data[14].buf);
    memset(&state,0,sizeof(state));memset(&fencing70,0,sizeof(fencing70));state.model=&model;
    model.name="70D";model.firmware_version=112;model.digic_version=5;capture.jp57_research=1;option="1";count=last_irq=0;
    state.edmac.read_conn[14]=12;state.edmac.write_conn[16]=23;
    state.edmac.ch[12]=(EDmacChState){.addr=0x200000+168064,.xa=4096,.xb=128,.xn=41,.flags=0x40050000};
    state.edmac.ch[16]=(EDmacChState){.addr=0x400000+54000,.xa=4096,.xb=752,.xn=13,.flags=0};
    state.edmac.conn_data[14]=(EDmacData){malloc(168064),168064};assert(state.edmac.conn_data[14].buf);
    fencing70_mmio(0xc0f1b330,MODE_WRITE,0x200000);fencing70_mmio(0xc0f1b334,MODE_WRITE,0x400000);
    fencing70_mmio(0xc0f1b338,MODE_WRITE,0xf00140);fencing70_mmio(0xc0f1b33c,MODE_WRITE,0);
}
int main(void)
{
    for(unsigned bad=0;bad<16;bad++){
        setup();void*data=state.edmac.conn_data[14].buf;
        switch(bad){
            case 0:option="0";break;case 1:model.name="EOSM";break;case 2:model.firmware_version=113;break;
            case 3:capture.jp57_research=0;break;case 4:state.edmac.read_conn[14]=11;break;
            case 5:state.edmac.write_conn[16]=24;break;case 6:state.edmac.ch[12].flags=0;break;
            case 7:state.edmac.ch[12].off1a=1;break;case 8:state.edmac.ch[12].addr++;break;
            case 9:state.edmac.ch[16].addr++;break;case 10:state.edmac.conn_data[14].data_size++;break;
            case 11:state.edmac.ch[12].xn++;break;case 12:fencing70_mmio(0xc0f1b338,MODE_WRITE,0);break;
            case 13:fencing70_mmio(0xc0f1b334,MODE_WRITE,UINT32_MAX);break;case 14:model.digic_version=4;break;
            case 15:state.edmac.ch[16].flags=0x40000000;break;
        }
        fencing70_mmio(0xc0f1b300,MODE_WRITE,1);assert(!count&&state.edmac.conn_data[14].buf==data);
    }
    setup();fencing70_mmio(0xc0f1b300,0,1);assert(!count);fencing70_mmio(0xc0f1b340,MODE_WRITE,8);assert(!count);
    fencing70_mmio(0xc0f1b300,MODE_WRITE,1);assert(count==1&&last_irq==0xd0&&!state.edmac.conn_data[14].buf);
    fencing70_poll();assert(count==1);
    state.edmac.conn_data[14]=(EDmacData){malloc(0x1000000),0x1000000};assert(state.edmac.conn_data[14].buf);
    state.edmac.ch[12]=(EDmacChState){.addr=0x400000+0x1000000,.xa=4096,.xb=0,.xn=4096,.flags=0x40050000};
    fencing70_mmio(0xc0f1b340,MODE_WRITE,7);assert(count==1);
    fencing70_mmio(0xc0f1b340,MODE_WRITE,8);assert(count==2&&last_irq==0xd1&&!state.edmac.conn_data[14].buf);
    fencing70_poll();assert(count==2);
    puts("Fencing research: 16 rejection cases, read-only/no-prior-FB refusal, exact FB/FC completion and no duplicate IRQ: PASS");
    return 0;
}
