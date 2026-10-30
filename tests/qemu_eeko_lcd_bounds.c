/* Exercise the actual research adapter with a small instrumented guest RAM map.
 * JPEG coding is stubbed here; the saved Canon preview is decoded separately.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MIRROR_EEKO_LCD_HOST_TEST
#define CACHING_BIT 0x40000000u
#define EEKO_SS 0
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define MIN(a,b) ((a)<(b)?(a):(b))
struct eeko_msg { uint8_t ch, cmd; uint32_t param, arg; };
static struct { uint8_t *jpeg; int jpeg_len; } cap;
static uint8_t ram[0x02000000];
static unsigned writes, frees, boxed;
static int no_reply_box;
static void eos_mem_read(uint32_t address, void *data, int size)
{
    assert(size > 0 && address <= sizeof(ram)-(unsigned)size);
    memcpy(data, ram+address, size);
}
static void eos_mem_write(uint32_t address, void *data, int size)
{
    assert(size > 0 && address <= sizeof(ram)-(unsigned)size);
    memcpy(ram+address, data, size); writes++;
}
static void eeko_free(uint32_t address)
{
    assert(address == 0x1f80200 || address == 0x1f80300); frees++;
}
static uint32_t eeko_box(const uint32_t *words, int count)
{
    assert(count == 3 && words[0] == 13 && words[1] == 0 && words[2] == 0);
    boxed++; return no_reply_box ? 0 : 0x1f90004;
}
static void make_jpeg(int width, int height, int level)
{
    assert(((width == 5472 && height == 3648) || (width == 160 && height == 120)) && level == 128);
    static uint8_t bytes[] = "syntheticJPEG";
    cap.jpeg = bytes; cap.jpeg_len = 13;
}
#include "../targets/70D.112/qemu/eeko_lcd_research.inc.c"

static struct eeko_msg setup(void)
{
    memset(ram+0x1f80000, 0, 0x400);
    memset(&lcd70, 0, sizeof(lcd70));
    memset(&thm70, 0, sizeof(thm70));
    writes = frees = boxed = 0; no_reply_box = 0;
    uint32_t region[] = {0x41f80000, 0x10000};
    memcpy(ram+0x1f80028, region, sizeof(region));
    uint32_t box[33] = {2,1,1,1,0,3,8,0x1f80200};
    box[32] = 0x1f80300;
    memcpy(ram+0x1f80080, box, sizeof(box));
    for (unsigned i = 0; i < 8; i++) {
        uint32_t chunk[] = {0x40100000 + i*0x1000, 8};
        memcpy(ram+0x1f80200+i*8, chunk, 8);
        memset(ram+0x100000+i*0x1000, 0xa5, 32);
    }
    return (struct eeko_msg){0,0,0xb00,0x41f80080};
}
static void word(uint32_t address, uint32_t value) { memcpy(ram+address,&value,4); }
int main(void)
{
    struct eeko_msg req, reply, start = {0,0,0xb01,0x1ca8c08e};
    req=setup(); assert(capture_70d_eeko_lcd(&start,&reply)==0 && !writes);
    assert(capture_70d_eeko_lcd(&req,&reply)==0 && lcd70.ready && !writes);
    assert(capture_70d_eeko_lcd(&start,&reply)==1);
    assert(reply.ch==3 && reply.cmd==0 && reply.param==0xb03 && reply.arg==0x1f90004);
    assert(writes==2 && frees==2 && boxed==1);
    assert(!memcmp(ram+0x100000,"syntheti",8) && ram[0x100008]==0xa5);
    assert(!memcmp(ram+0x101000,"cJPEG",5) && ram[0x101005]==0xa5);
    assert(ram[0x102000]==0xa5);
    assert(capture_70d_eeko_lcd(&start,&reply)==0 && writes==2);
    /* Malformed dimensions/mode, pool boundary, overlap, wrap, memory/size bounds. */
    const uint32_t invalid[][2] = {
        {0x1f80080,1}, {0x1f80098,17}, {0x1f80098,0}, {0x1f8009c,0x1f8fff0},
        {0x1f80100,0}, {0x1f80208,0x100004}, {0x1f80200,0xfffffff0},
        {0x1f80200,0x1ffffffc}, {0x1f80204,0x01000001}, {0x1f80204,0},
    };
    for (unsigned i=0;i<ARRAY_SIZE(invalid);i++) {
        req=setup(); word(invalid[i][0],invalid[i][1]);
        assert(capture_70d_eeko_lcd(&req,&reply)==0 && !lcd70.ready);
        assert(capture_70d_eeko_lcd(&start,&reply)==0 && !writes && !boxed);
    }
    req=setup();req.ch=2;assert(!capture_70d_eeko_lcd(&req,&reply) && !lcd70.ready);
    req=setup();req.cmd=4;assert(!capture_70d_eeko_lcd(&req,&reply) && !lcd70.ready);
    req=setup();req.param=0xb02;assert(!capture_70d_eeko_lcd(&req,&reply) && !lcd70.ready);
    req=setup();capture_70d_eeko_lcd(&req,&reply);no_reply_box=1;
    assert(!capture_70d_eeko_lcd(&start,&reply) && !writes && !frees);
    req=setup();capture_70d_eeko_lcd(&req,&reply);
    for(unsigned i=0;i<8;i++)lcd70.chunks[i][1]=1;
    assert(!capture_70d_eeko_lcd(&start,&reply) && !writes && !boxed);
    /* Canon coalesces the next shot's suite into one chunk; intermediate
     * fragmentation is also valid when the whole list remains bounded. */
    for(unsigned count=1;count<=16;count++) {
        req=setup();word(0x1f80098,count);
        for(unsigned i=0;i<count;i++) {
            word(0x1f80200+i*8,0x40100000+i*0x1000);
            word(0x1f80204+i*8,64);
        }
        assert(!capture_70d_eeko_lcd(&req,&reply) && lcd70.ready && lcd70.count==count);
        assert(capture_70d_eeko_lcd(&start,&reply)==1 && writes==1 && frees==2);
    }
    req=setup();req.param=0xc01;
    uint32_t thm[] = {0,0,0,0xc1940,0xc18c0,87,1,0x1f80200};
    memcpy(ram+0x1f80080,thm,sizeof(thm));word(0x1f80204,65536);
    start.param=0xc03;
    assert(!capture_70d_eeko_lcd(&start,&reply) && !writes);
    assert(!capture_70d_eeko_lcd(&req,&reply) && thm70.ready);
    assert(capture_70d_eeko_lcd(&start,&reply)==1);
    assert(reply.param==0xc01 && writes==1 && frees==1 && boxed==1);
    assert(!memcmp(ram+0x100000,"syntheticJPEG",13) && ram[0x10000d]==0xa5);
    assert(!capture_70d_eeko_lcd(&start,&reply) && writes==1);
    const uint32_t bad_thm[][2] = {{0x1f80080,1},{0x1f80098,2},
        {0x1f8009c,0x1f8fffc},{0x1f80204,65535},{0x1f80200,0x1fffffff}};
    for(unsigned i=0;i<ARRAY_SIZE(bad_thm);i++) {
        req=setup();req.param=0xc01;memcpy(ram+0x1f80080,thm,sizeof(thm));
        word(0x1f80204,65536);word(bad_thm[i][0],bad_thm[i][1]);
        assert(!capture_70d_eeko_lcd(&req,&reply) && !thm70.ready);
        assert(!capture_70d_eeko_lcd(&start,&reply) && !writes && !boxed);
    }
    puts("LCD adapter: chunk boundaries, refusal paths, one-shot completion passed");
}
