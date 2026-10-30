/* SPDX-License-Identifier: GPL-2.0-or-later
 * Optical-registration diagnostic, independent of the cell-permutation oracle.
 * Each CFA plane samples the SAME affine spatial ramp with a fixed plane gain.
 * A geometric mirror must evaluate that plane at the reflected pixel location.
 * No Canon APIs, captured data, demosaic tuning or camera ownership assumptions.
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fx_mirror_sensor.h"
#include "fx_mirror_edges.h"
#ifdef CFA_REGISTERED
#include "fx_mirror_registered.h"
#endif
enum {W=64,H=48,PITCH=W*14/8,AX=4,AY=12};
static unsigned phase(unsigned x,unsigned y){return (y&1)*2+(x&1);}
static unsigned response(unsigned channel,unsigned x,unsigned y){return 512+channel*1024+AX*x+AY*y;}
/* Bit-by-bit Canon14 encoder/decoder, independent of production word shuffles. */
static void store(unsigned char*row,unsigned x,unsigned value)
{
    for(unsigned k=0;k<14;k++){
        unsigned bit=x*14+k,at=(bit/16)*2+(15-bit%16)/8,mask=1u<<((15-bit%16)%8);
        if(value&(1u<<(13-k)))row[at]|=mask;else row[at]&=(unsigned char)~mask;
    }
}
static unsigned load(const unsigned char*row,unsigned x)
{
    unsigned v=0;
    for(unsigned k=0;k<14;k++){
        unsigned bit=x*14+k,at=(bit/16)*2+(15-bit%16)/8;
        v=(v<<1)|((row[at]>>((15-bit%16)%8))&1);
    }
    return v;
}
static unsigned reflected_pixel(unsigned at,unsigned size,unsigned div,unsigned low,unsigned high)
{
    unsigned border=2*((size/2)/div);
#ifdef CFA_REGISTERED
    /* A common, integer-valued axis for all four color planes: the original
     * raw samples remain geometrically registered with no resampling. */
    if(low&&at<border)return 2*(border-1)-at;
    if(high&&at>=size-border)return 2*(size-border)-at;
#else
    if(low&&at<border)return 2*border-1-at;
    if(high&&at>=size-border)return 2*(size-border)-1-at;
#endif
    return at;
}
/* A separate reference resamples one CFA plane at the desired location.
 * Exact affine-ramp checks below exclude the outermost source row/column,
 * where edge extension is a separate policy rather than known scene data. */
#ifndef CFA_REGISTERED
static unsigned registered_reference(const unsigned char*source,unsigned channel,unsigned x,unsigned y,unsigned dx,unsigned dy)
{
    unsigned x0=x-((x^dx)&1),x1=x+((x^dx)&1);
    unsigned y0=y-((y^dy)&1),y1=y+((y^dy)&1);
    assert(phase(x0,y0)==channel&&phase(x1,y1)==channel);
    return (load(source+y0*PITCH,x0)+load(source+y0*PITCH,x1)+
            load(source+y1*PITCH,x0)+load(source+y1*PITCH,x1)+2)/4;
}
#endif
#ifdef CFA_REGISTERED
static unsigned bounded(unsigned x,unsigned parity,unsigned begin,unsigned end)
{
    unsigned first=begin+parity,last=end-2+parity;
    return x<first?first:x>last?last:x;
}
static unsigned extended_reference(const unsigned char*source,unsigned x,unsigned y,unsigned dx,unsigned dy,const uint32_t r[4])
{
    unsigned ox=(x^dx)&1,oy=(y^dy)&1;
    unsigned x0=bounded(x-ox,dx&1,r[1],r[3]),x1=bounded(x+ox,dx&1,r[1],r[3]);
    unsigned y0=bounded(y-oy,dy&1,r[0],r[2]),y1=bounded(y+oy,dy&1,r[0],r[2]);
    unsigned a=(load(source+y0*PITCH,x0)+load(source+y1*PITCH,x0)+1)/2;
    unsigned b=(load(source+y0*PITCH,x1)+load(source+y1*PITCH,x1)+1)/2;
    return (a+b+1)/2;
}
#endif
int main(void)
{
    const unsigned masks[]={1,2,4,8,3,12,15};
    const uint32_t region[]={2,4,H-2,W-4};
    unsigned char original[PITCH*H]={0},output[PITCH*H];
    for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++)store(original+y*PITCH,x,response(phase(x,y),x,y));
    unsigned cases=0,total_registration=0,total_transport=0,total_reference=0,total_interior=0,total_samples=0,total_boundary=0;
    for(unsigned k=0;k<7;k++)for(unsigned dx=2;dx<=6;dx++)for(unsigned dy=2;dy<=6;dy++){
        unsigned mask=masks[k];
        if((!(mask&3)&&dx!=2)||(!(mask&12)&&dy!=2)||((mask&3)==3&&dx==2)||((mask&12)==12&&dy==2))continue;
        memcpy(output,original,sizeof(output));
        gl_frame frame={output,sizeof(output),W,H,PITCH,GL_CANON14,0,16383};
        fx_params params={{FX_MIRROR_EDGES,mask,dx,dy}};fx_mirror_raw map;
        assert(fx_mirror_raw_prepare(&map,&frame,region,&params,0)==FX_OK);
        /* Record original source coordinates before the in-place transform. */
        unsigned coords[H][W][2];
        for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++)assert(fx_mirror_raw_point(&map,x,y,coords[y][x])==FX_OK);
#ifdef CFA_REGISTERED
        unsigned char workspace[2*PITCH];
        assert(fx_mirror_registered_apply(&map,output,sizeof(output),workspace,sizeof(workspace))==FX_OK);
#else
        assert(fx_mirror_sensor_axial(&map,output,sizeof(output))==FX_OK);
#endif
        unsigned registration=0,transport=0,reference=0,tested_reference=0,interior=0,boundary=0;
        int low[4]={100000,100000,100000,100000},high[4]={-100000,-100000,-100000,-100000};
        for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++){
            unsigned actual=load(output+y*PITCH,x),*xy=coords[y][x],channel=phase(x,y);
#ifndef CFA_REGISTERED
            transport+=actual!=response(phase(xy[0],xy[1]),xy[0],xy[1]);
#else
            (void)xy;
#endif
            if(x<region[1]||x>=region[3]||y<region[0]||y>=region[2]){assert(actual==load(original+y*PITCH,x));continue;}
            unsigned sx=region[1]+reflected_pixel(x-region[1],region[3]-region[1],dx,mask&1,mask&2);
            unsigned sy=region[0]+reflected_pixel(y-region[0],region[2]-region[0],dy,mask&4,mask&8);
#ifdef CFA_REGISTERED
            transport+=actual!=extended_reference(original,sx,sy,x,y,region);
#endif
            int error=(int)actual-(int)response(channel,sx,sy);registration+=error!=0;
            if(sx!=x||sy!=y){if(error<low[channel])low[channel]=error;if(error>high[channel])high[channel]=error;}
#ifdef CFA_REGISTERED
            assert(phase(sx,sy)==channel);
            tested_reference++;interior+=error!=0;reference+=load(original+sy*PITCH,sx)!=response(channel,sx,sy);
#else
            if(sx>region[1]&&sx+1<region[3]&&sy>region[0]&&sy+1<region[2]){
                tested_reference++;interior+=error!=0;reference+=registered_reference(original,channel,sx,sy,x,y)!=response(channel,sx,sy);
            }else boundary++;
#endif
        }
        printf("CFA_CASE={\"mask\":%u,\"dx\":%u,\"dy\":%u,\"transport_mismatches\":%u,\"registration_mismatches\":%u,\"reference_mismatches\":%u,\"reference_samples\":%u,\"interior_registration_mismatches\":%u,\"boundary_extension_samples\":%u,\"phase_error_min\":[%d,%d,%d,%d],\"phase_error_max\":[%d,%d,%d,%d]}\n",
            mask,dx,dy,transport,registration,reference,tested_reference,interior,boundary,low[0],low[1],low[2],low[3],high[0],high[1],high[2],high[3]);
        cases++;total_registration+=registration;total_transport+=transport;total_reference+=reference;
        total_interior+=interior;total_samples+=tested_reference;total_boundary+=boundary;
    }
    assert(cases==44);
    printf("CFA_TOTAL={\"cases\":%u,\"transport_mismatches\":%u,\"registration_mismatches\":%u,\"reference_mismatches\":%u,\"reference_samples\":%u,\"interior_registration_mismatches\":%u,\"boundary_extension_samples\":%u}\n",cases,total_transport,total_registration,total_reference,total_samples,total_interior,total_boundary);
    return total_transport||total_reference?1:0;
}
