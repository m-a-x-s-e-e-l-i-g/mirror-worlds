/* SPDX-License-Identifier: GPL-2.0-or-later
 * Bounded reference encoder for QEMU research, not a camera module.
 * ITU T.81 Annex H: SOF3, two components, predictor 1, 14-bit samples.
 * https://www.w3.org/Graphics/JPEG/itu-t81.pdf
 */
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>

int mirror_lj14_encode(const uint16_t*,uint32_t,uint32_t,uint8_t**,size_t*);

typedef struct { uint8_t *p; size_t n,cap,limit; uint32_t bits; unsigned used; int failed; } writer;
static void byte(writer *w, unsigned v)
{
    if (w->failed) return;
    if (w->n==w->cap) {
        size_t cap=w->cap?w->cap*2:4096;
        if (cap>w->limit) cap=w->limit;
        if (cap<=w->n) { w->failed=1;return; }
        void *p=realloc(w->p,cap);
        if (!p) { w->failed=1;return; }
        w->p=p;w->cap=cap;
    }
    w->p[w->n++]=(uint8_t)v;
}
static void word(writer *w, unsigned v) { byte(w,v>>8);byte(w,v); }
static void marker(writer *w, unsigned v) { byte(w,255);byte(w,v); }
static void bits(writer *w, unsigned v, unsigned n)
{
    while (n--) {
        w->bits=(w->bits<<1)|((v>>n)&1u);
        if (++w->used==8) {
            byte(w,w->bits);
            if ((w->bits&255)==255) byte(w,0);
            w->bits=w->used=0;
        }
    }
}
int mirror_lj14_encode(const uint16_t *pixels,uint32_t width,uint32_t height,uint8_t **out,size_t *size)
{
    if (!out||!size) return -1;
    *out=NULL;*size=0;
    if (!pixels||!width||width%2||width>131070||!height||height>65535) return -1;
    if (height>24000000u/width) return -1;
    size_t count=(size_t)width*height;
    writer w={.limit=count*5+512};
    marker(&w,0xd8);
    marker(&w,0xc4);word(&w,34);byte(&w,0);
    for (unsigned i=1;i<=16;i++) byte(&w,i==5?15:0);
    for (unsigned i=0;i<15;i++) byte(&w,i);
    marker(&w,0xc3);word(&w,14);byte(&w,14);word(&w,height);word(&w,width/2);byte(&w,2);
    for (unsigned i=1;i<=2;i++) { byte(&w,i);byte(&w,0x11);byte(&w,0); }
    marker(&w,0xda);word(&w,10);byte(&w,2);
    for (unsigned i=1;i<=2;i++) { byte(&w,i);byte(&w,0); }
    byte(&w,1);byte(&w,0);byte(&w,0);
    for (uint32_t y=0;y<height;y++) {
        for (uint32_t x=0;x<width;x++) {
            size_t i=(size_t)y*width+x;
            unsigned value=pixels[i];
            if (value>16383) { free(w.p);return -1; }
            int prediction=x>=2?pixels[i-2]:y?pixels[i-width]:8192;
            int diff=(int)value-prediction;
            unsigned mag=diff<0?-diff:diff,category=0;
            for (unsigned m=mag;m;m>>=1) category++;
            bits(&w,category,5);
            if (category) bits(&w,diff<0?diff+((1u<<category)-1u):(unsigned)diff,category);
        }
    }
    if (w.used) bits(&w,(1u<<(8-w.used))-1,8-w.used);
    marker(&w,0xd9);
    if (w.failed) { free(w.p);return -1; }
    *out=w.p;*size=w.n;
    return 0;
}
