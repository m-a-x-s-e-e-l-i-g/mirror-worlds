/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade).
 * Three graph states, five cells per byte (3^5=243). Decode/reset tables
 * avoid runtime division by powers of three on ARMv5. Input bytes are private,
 * initialized to zero, and remain <243 under trit_mark/clear_refs.
 * PROCESSED dominates REFERENCED, matching the old processed/reference bits.
 * Tables are checked exhaustively against independent base-three arithmetic. */
#ifndef FX_MIRROR_TRITS_H
#define FX_MIRROR_TRITS_H
#include <stdint.h>
static const uint16_t trit_decode[243]={
    0,1,2,4,5,6,8,9,10,16,17,18,20,21,22,
    24,25,26,32,33,34,36,37,38,40,41,42,64,65,66,
    68,69,70,72,73,74,80,81,82,84,85,86,88,89,90,
    96,97,98,100,101,102,104,105,106,128,129,130,132,133,134,
    136,137,138,144,145,146,148,149,150,152,153,154,160,161,162,
    164,165,166,168,169,170,256,257,258,260,261,262,264,265,266,
    272,273,274,276,277,278,280,281,282,288,289,290,292,293,294,
    296,297,298,320,321,322,324,325,326,328,329,330,336,337,338,
    340,341,342,344,345,346,352,353,354,356,357,358,360,361,362,
    384,385,386,388,389,390,392,393,394,400,401,402,404,405,406,
    408,409,410,416,417,418,420,421,422,424,425,426,512,513,514,
    516,517,518,520,521,522,528,529,530,532,533,534,536,537,538,
    544,545,546,548,549,550,552,553,554,576,577,578,580,581,582,
    584,585,586,592,593,594,596,597,598,600,601,602,608,609,610,
    612,613,614,616,617,618,640,641,642,644,645,646,648,649,650,
    656,657,658,660,661,662,664,665,666,672,673,674,676,677,678,
    680,681,682,
};
static const unsigned char trit_without_refs[243]={
    0,1,0,3,4,3,0,1,0,9,10,9,12,13,12,
    9,10,9,0,1,0,3,4,3,0,1,0,27,28,27,
    30,31,30,27,28,27,36,37,36,39,40,39,36,37,36,
    27,28,27,30,31,30,27,28,27,0,1,0,3,4,3,
    0,1,0,9,10,9,12,13,12,9,10,9,0,1,0,
    3,4,3,0,1,0,81,82,81,84,85,84,81,82,81,
    90,91,90,93,94,93,90,91,90,81,82,81,84,85,84,
    81,82,81,108,109,108,111,112,111,108,109,108,117,118,117,
    120,121,120,117,118,117,108,109,108,111,112,111,108,109,108,
    81,82,81,84,85,84,81,82,81,90,91,90,93,94,93,
    90,91,90,81,82,81,84,85,84,81,82,81,0,1,0,
    3,4,3,0,1,0,9,10,9,12,13,12,9,10,9,
    0,1,0,3,4,3,0,1,0,27,28,27,30,31,30,
    27,28,27,36,37,36,39,40,39,36,37,36,27,28,27,
    30,31,30,27,28,27,0,1,0,3,4,3,0,1,0,
    9,10,9,12,13,12,9,10,9,0,1,0,3,4,3,
    0,1,0,
};
static const unsigned char trit_power[5]={1,3,9,27,81};
static inline unsigned trit_state(const unsigned char*states,unsigned id)
{return (trit_decode[states[id/5]]>>((id%5)*2))&3;}
/* value is 1 (processed) or 2 (referenced); processed always takes priority. */
static inline void trit_mark(unsigned char*states,unsigned id,unsigned value)
{
    unsigned byte=id/5,slot=id%5,packed=states[byte];
    unsigned old=(trit_decode[packed]>>(slot*2))&3;
    unsigned next=value==1||old==1?1:2;
    states[byte]=(unsigned char)((int)packed+((int)next-(int)old)*trit_power[slot]);
}
static inline void trit_clear_refs(unsigned char*states,unsigned count)
{
    for(unsigned i=0;i<(count+4)/5;i++)states[i]=trit_without_refs[states[i]];
}
#endif
