/* Included by capture.c after make_jpeg(). Local 70D.112 emulator research.
 * Main: ff41e6b8/ff41e9fc. Eeko ROM: ffb73894..ffb739c6,
 * ffb6d33e (5472 x 3648), ffb6cb6c (length/status completion).
 * This supplies a flat synthetic JPEG, not Eeko's RAW development or colour.
 */
#ifndef MIRROR_EEKO_LCD_HOST_TEST
#include "hw/eos/eeko.h"
#endif

int capture_70d_eeko_lcd(const struct eeko_msg *, struct eeko_msg *);

static struct {
    uint32_t list, nested, count, chunks[16][2];
    int ready;
} lcd70;
static struct {
    uint32_t list, address, capacity;
    int ready;
} thm70;

static int lcd70_ram(uint32_t address, uint32_t bytes)
{
    return address >= 0x100000 && address < 0x20000000 &&
           bytes && bytes <= 0x20000000 - address;
}

static int lcd70_pool(uint32_t address, uint32_t bytes)
{
    uint32_t region[2];
    eos_mem_read(0x01f80028, region, sizeof(region));
    region[0] &= ~CACHING_BIT;
    return lcd70_ram(region[0], region[1]) && address >= region[0] + 4 &&
           address < region[0] + region[1] &&
           bytes <= region[0] + region[1] - address;
}

int capture_70d_eeko_lcd(const struct eeko_msg *req, struct eeko_msg *out)
{
    if (req->ch >= 2 || req->cmd != EEKO_SS) return 0;
    /* Thumbnail: main ff41dec4/ff41e04c; Eeko ffb737d8..ffb73870.
     * C00 sets DMA handles, C01 supplies parameters/chunks, C03 starts;
     * completion is C01 with {JPEG length, status, reserved}.
     * The first placeholder uses a 160x120 DCF thumbnail; its physical
     * development/resizing is not emulated. */
    if (req->param == 0xc01) {
        uint32_t box[8], chunk[2], address = req->arg & ~CACHING_BIT;
        thm70.ready = 0;
        if (!lcd70_pool(address, sizeof(box))) return 0;
        eos_mem_read(address, box, sizeof(box));
        if (box[0] || box[1] || box[2] || box[6] != 1 ||
            !lcd70_pool(box[7], sizeof(chunk))) return 0;
        eos_mem_read(box[7], chunk, sizeof(chunk)); chunk[0] &= ~CACHING_BIT;
        if (!lcd70_ram(chunk[0], chunk[1]) || chunk[1] != 65536) return 0;
        thm70.list = box[7]; thm70.address = chunk[0];
        thm70.capacity = chunk[1]; thm70.ready = 1;
        fprintf(stderr, "[LCD70R] captured C01: bounded thumbnail output chunk\n");
        return 0;
    }
    if (req->param == 0xc03 && thm70.ready) {
        thm70.ready = 0;
        if (!lcd70_ram(req->arg & ~CACHING_BIT, 2)) return 0;
        make_jpeg(160, 120, 128);
        if (!cap.jpeg || cap.jpeg_len <= 0 || (unsigned)cap.jpeg_len > thm70.capacity) return 0;
        uint32_t result[] = {cap.jpeg_len, 0, 0};
        uint32_t reply = eeko_box(result, ARRAY_SIZE(result));
        if (!reply) return 0;
        eos_mem_write(thm70.address, cap.jpeg, cap.jpeg_len);
        eeko_free(thm70.list);
        out[0] = (struct eeko_msg){.ch = 3, .cmd = EEKO_SS, .param = 0xc01, .arg = reply};
        fprintf(stderr, "[LCD70R] synthetic flat thumbnail 160x120: %d bytes\n", cap.jpeg_len);
        return 1;
    }
    if (req->param == 0xb00) {
        uint32_t box[33], address = req->arg & ~CACHING_BIT;
        lcd70.ready = 0;
        if (!lcd70_pool(address, sizeof(box))) return 0;
        eos_mem_read(address, box, sizeof(box));
        /* Restrict this first experiment to the one observed full-RAW job. */
        const uint32_t prefix[] = {2, 1, 1, 1, 0, 3};
        if (memcmp(box, prefix, sizeof(prefix)) ||
            !box[6] || box[6] > ARRAY_SIZE(lcd70.chunks) ||
            !lcd70_pool(box[7], box[6] * 8) ||
            !lcd70_pool(box[32], 4)) {
            fprintf(stderr, "[LCD70R] unsupported B00 parameters; no completion\n");
            return 0;
        }
        eos_mem_read(box[7], lcd70.chunks, box[6] * 8);
        for (unsigned i = 0; i < box[6]; i++) {
            lcd70.chunks[i][0] &= ~CACHING_BIT;
            uint32_t a = lcd70.chunks[i][0], n = lcd70.chunks[i][1];
            if (!lcd70_ram(a, n) || n > 16 * 1024 * 1024) return 0;
            for (unsigned j = 0; j < i; j++) {
                uint32_t b = lcd70.chunks[j][0], m = lcd70.chunks[j][1];
                if (a < b + m && b < a + n) return 0;
            }
        }
        lcd70.list = box[7]; lcd70.nested = box[32]; lcd70.count = box[6]; lcd70.ready = 1;
        fprintf(stderr, "[LCD70R] captured B00: %u bounded JPEG output chunks\n", lcd70.count);
        return 0; /* B00 configures; it does not receive an acknowledgement. */
    }
    if (req->param != 0xb01 || !lcd70.ready) return 0;
    lcd70.ready = 0;
    if (!lcd70_ram(req->arg & ~CACHING_BIT, 2)) return 0;
    make_jpeg(5472, 3648, 128);
    size_t capacity = 0;
    for (unsigned i = 0; i < lcd70.count; i++) capacity += lcd70.chunks[i][1];
    if (!cap.jpeg || cap.jpeg_len <= 0 || (size_t)cap.jpeg_len > capacity) return 0;
    uint32_t result[] = {cap.jpeg_len, 0, 0};
    uint32_t reply = eeko_box(result, ARRAY_SIZE(result));
    if (!reply) return 0;
    size_t written = 0;
    for (unsigned i = 0; i < lcd70.count && written < (size_t)cap.jpeg_len; i++) {
        size_t n = MIN((size_t)lcd70.chunks[i][1], (size_t)cap.jpeg_len - written);
        eos_mem_write(lcd70.chunks[i][0], cap.jpeg + written, n);
        written += n;
    }
    eeko_free(lcd70.list); eeko_free(lcd70.nested);
    out[0] = (struct eeko_msg){.ch = 3, .cmd = EEKO_SS, .param = 0xb03, .arg = reply};
    fprintf(stderr, "[LCD70R] synthetic flat JPEG 5472x3648: %d bytes, B03 result %08X\n",
            cap.jpeg_len, reply);
    return 1;
}
