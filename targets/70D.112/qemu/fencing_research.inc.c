/* SPDX-License-Identifier: GPL-2.0-or-later
 * 70D.112 completion-only model for the observed FB/FC preprocessing path.
 * No image processing is modeled here. Existing dummy FB output is unchanged.
 * ROM ff42e134 / ff42e0d0 are registered on interrupts D0 / D1. Start writes
 * come from ff2c1b1c (B300=1) and ff2c1b4c (B340=8). Both require completed
 * connection-14 DMA with the exact observed geometry, flags and pointer.
 * Explicit research opt-in; never changes module clocks or shutter deadlines.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static struct {
    uint32_t input, output, geometry, reserved;
    int fb_pending, fc_pending, fb_done;
} fencing70;

static int fencing70_enabled(void)
{
    const char*enabled=getenv("QEMU_EOS_FENCING_RESEARCH");
    return enabled&&!strcmp(enabled,"1")&&eos_state->model->capture&&
        eos_state->model->capture->jp57_research&&!strcmp(eos_state->model->name,"70D")&&
        eos_state->model->firmware_version==112&&eos_state->model->digic_version==5;
}
static int fencing70_ram(uint32_t a,uint32_t n)
{return a>=0x100000&&a<0x20000000&&n&&n<=0x20000000-a;}
static int fencing70_offsets(const EDmacChState*c)
{return !c->ya&&!c->yb&&!c->yn&&!c->off1a&&!c->off1b&&!c->off2a&&!c->off2b&&!c->off3;}
static void fencing70_consume(unsigned irq)
{
    /* engine.c schedules the input DMA IRQ at floor(bytes/rate/256us)+1.
     * Its host buffer/pointer advance before that IRQ fires. Completion must
     * follow the DMA IRQ, or Canon unregisters its handler too early. */
    uint32_t bytes=eos_state->edmac.conn_data[14].data_size;
    unsigned delay=(unsigned)((uint64_t)bytes*1000000/(200*1024*1024)/256)+2;
    free(eos_state->edmac.conn_data[14].buf);
    eos_state->edmac.conn_data[14].buf=NULL;eos_state->edmac.conn_data[14].data_size=0;
    eos_trigger_int(irq,delay);
    fprintf(stderr,"[FENCE70R] bounded synthetic preprocessing completion IRQ %X after %u DMA ticks\n",irq,delay);
}
static void fencing70_poll(void)
{
    if(!fencing70_enabled()||eos_state->edmac.read_conn[14]!=12)return;
    const EDmacChState*r=&eos_state->edmac.ch[12],*w=&eos_state->edmac.ch[16];
    const EDmacData*data=&eos_state->edmac.conn_data[14];
    if(!data->buf||r->flags!=0x40050000||!fencing70_offsets(r))return;
    if(fencing70.fb_pending&&fencing70.geometry==0x00f00140&&!fencing70.reserved&&
       fencing70_ram(fencing70.input,168064)&&fencing70_ram(fencing70.output,54000)&&
       r->xa==4096&&r->xb==128&&r->xn==41&&data->data_size==168064&&r->addr==fencing70.input+168064&&
       /* Canon's completed write ISR has cleared its flags by block start. */
       eos_state->edmac.write_conn[16]==23&&!w->flags&&fencing70_offsets(w)&&
       w->xa==4096&&w->xb==752&&w->xn==13&&w->addr==fencing70.output+54000){
        fencing70.fb_pending=0;fencing70.fb_done=1;fencing70_consume(0xd0);
    }else if(fencing70.fc_pending&&fencing70.fb_done&&
        fencing70_ram(fencing70.output,0x1000000)&&r->xa==4096&&!r->xb&&r->xn==4096&&
        data->data_size==0x1000000&&r->addr==fencing70.output+0x1000000){
        fencing70.fc_pending=fencing70.fb_done=0;fencing70_consume(0xd1);
    }
}
static void fencing70_mmio(uint32_t address,unsigned type,uint32_t value)
{
    if(!(type&MODE_WRITE)||!fencing70_enabled())return;
    switch(address){
        case 0xc0f1b330:fencing70.input=value;break;
        case 0xc0f1b334:fencing70.output=value;break;
        case 0xc0f1b338:fencing70.geometry=value;break;
        case 0xc0f1b33c:fencing70.reserved=value;break;
        case 0xc0f1b300:
            fencing70.fb_pending=value==1;
            if(!value)fencing70.fc_pending=fencing70.fb_done=0;
            break;
        case 0xc0f1b340:fencing70.fc_pending=value==8;break;
        default:return;
    }
    fencing70_poll();
}
