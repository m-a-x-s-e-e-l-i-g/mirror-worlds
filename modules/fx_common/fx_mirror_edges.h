/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef FX_MIRROR_EDGES_H
#define FX_MIRROR_EDGES_H
#include "fx_effect.h"
/* Versioned parameter tag preserves the historical angular mapper ABI. */
#define FX_MIRROR_EDGES 180u
#define FX_EDGE_LEFT 1u
#define FX_EDGE_RIGHT 2u
#define FX_EDGE_TOP 4u
#define FX_EDGE_BOTTOM 8u
static inline int fx_edges_valid(const fx_params*p)
{
    if(!p||p->value[0]!=FX_MIRROR_EDGES||p->value[2]<2||p->value[2]>6||p->value[3]<2||p->value[3]>6)return 0;
    unsigned mask=p->value[1];
    if(mask!=1&&mask!=2&&mask!=4&&mask!=8&&mask!=3&&mask!=12&&mask!=15)return 0;
    return !((mask&3)==3&&p->value[2]==2)&&!((mask&12)==12&&p->value[3]==2);
}
/* Each destination maps DIRECTLY to an untouched source interval. For paired
 * borders, denominator >=3 leaves enough original center for either fold.
 * Units are Bayer cells for RAW, chroma pairs for preview X and rows for Y. */
static inline unsigned fx_edge_coordinate(unsigned at,unsigned extent,unsigned divisor,unsigned low,unsigned high)
{
    unsigned border=extent/divisor;
    if(low&&at<border)return border*2-1-at;
    if(high&&at>=extent-border)return (extent-border)*2-1-at;
    return at;
}
#endif
