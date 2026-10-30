/* Local 70D.112 QEMU research, not camera code. */
#include "qemu/osdep.h"
#include "hw/eos/eos.h"
#include "hw/eos/model_list.h"
#include "hw/eos/capture.h"

static uint32_t regs[1024];
static int started;
static int done;
static uint8_t *stream;
static size_t stream_size, stream_pos;
int mirror_lj14_encode(const uint16_t*,uint32_t,uint32_t,uint8_t**,size_t*);
static int enabled(void)
{
    return eos_state->model->capture && eos_state->model->capture->jp57_research;
}
int capture_jp57_mmio(unsigned off, unsigned type, unsigned value, unsigned *ret)
{
    if (!enabled()) return 0;
    if (off >= sizeof(regs) || (off & 3)) return 0;
    if (type & MODE_WRITE) {
        regs[off / 4] = value;
        if (off == 0) {
            started = !!(value & 1);done=0;
            if (!started) { free(stream);stream=NULL;stream_size=stream_pos=0; }
            else if ((regs[1]&15)==7) { done=1;started=0; }
        }
        if (off == 0x44 && (value & 0x400)) done=0;
    }
    *ret = regs[off / 4];
    if (off == 0) *ret = 0x1010000 | (started&&!done);
    if (off == 0x30) *ret = 0x1ff;
    if (off == 0x44) *ret = done?0x400:0;
    if (off == 0x24 && !(type & MODE_WRITE)) *ret = stream_size;
    static unsigned last[1024];static uint8_t seen[1024];
    if (off < 0x100 && ((type & MODE_WRITE)||!seen[off/4]||last[off/4]!=*ret))
        fprintf(stderr,"[JP57R] %c %04X value=%08X ret=%08X pc=%08X\n", (type & MODE_WRITE)?'W':'R',off,value,*ret,CURRENT_CPU->env.regs[15]);
    last[off/4]=*ret;seen[off/4]=1;
    return 1;
}
int capture_jp57_pending(int conn)
{
    return enabled() && conn == 45 && (!stream || stream_pos>=stream_size);
}
static uint16_t raw14(const uint8_t *data,size_t bytes,size_t index)
{
    size_t bit=index*14,word=bit/16,off=bit%16;
    size_t pos=word*2;
    uint32_t a=data[pos]|data[pos+1]<<8,b=0;
    if(pos+3<bytes)b=data[pos+2]|data[pos+3]<<8;
    return (((a<<16)|b)>>(18-off))&16383;
}
int capture_jp57_input(int conn, const void *data, int size)
{
    if (!enabled() || !started || conn!=1 || stream) return 0;
    fprintf(stderr,"[JP57R] input conn=%d bytes=%d frame=%08X components=%08X\n",conn,size,regs[0x80/4],regs[0x84/4]);
    unsigned width=regs[0x80/4]&65535,height=regs[0x80/4]>>16;
    if(!width||!height||width>3000||height>4000||regs[0x84/4]!=0x20e||(regs[1]&15)!=2) return 0;
    size_t plane=(size_t)width*height,count=plane*2;
    if((size_t)size!=count*14/8) { fprintf(stderr,"[JP57R] incomplete or unsupported input geometry\n");return 0; }
    uint16_t *pixels=malloc(count*2);assert(pixels);
    /* Preserve the DMA sequence: all left-half rows, then all right-half
     * rows. Canon's CR2 c640 tag describes two 2784-wide slices. The JPEG
     * components take adjacent values from that sequence; interleaving
     * corresponding left/right pixels corrupts the decoded CR2 ordering. */
    for(size_t i=0;i<count;i++)pixels[i]=raw14(data,size,i);
    int result=mirror_lj14_encode(pixels,width*2,height,&stream,&stream_size);
    fprintf(stderr,"[JP57R] encode result=%d size=%zu, DMA slice order preserved\n",result,stream_size);
    const char *dir=getenv("QEMU_EOS_JP57_CAPTURE_DIR");
    if(dir) {
        char path[512];snprintf(path,sizeof(path),"%s/jp57-input.u16",dir);
        FILE *f=fopen(path,"wb");if(f){fwrite(pixels,2,count,f);fclose(f);}
        snprintf(path,sizeof(path),"%s/jp57-output.ljpeg",dir);
        f=fopen(path,"wb");if(f&&stream){fwrite(stream,1,stream_size,f);}if(f)fclose(f);
        snprintf(path,sizeof(path),"%s/jp57-layout.json",dir);
        f=fopen(path,"w");if(f){fputs("{\"input_order\":\"dma-slices\",\"slices\":2,\"slice_width\":2784,\"height\":3708}\n",f);fclose(f);}
    }
    free(pixels);
    return result==0;
}
int capture_jp57_fill(int conn,void *data,int size)
{
    if(!enabled()||conn!=45||!stream||stream_pos>=stream_size)return 0;
    size_t n=MIN((size_t)size,stream_size-stream_pos);
    memset(data,0,size);memcpy(data,stream+stream_pos,n);stream_pos+=n;
    fprintf(stderr,"[JP57R] output %zu/%zu bytes, requested %d\n",stream_pos,stream_size,size);
    return 1;
}
void capture_jp57_output_progress(int conn,int delay)
{
    if(!enabled()||conn!=45||!stream||stream_pos<stream_size||done)return;
    done=1;
    eos_trigger_int_after_progress(0xa3,delay+4);
}
