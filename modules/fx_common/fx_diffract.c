/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade).
 * Stylized dispersed star/ring kernel, not a wave-optics simulation.
 * Source/old display pixels remain immutable. No heap, IO or libm imports. */
#include "fx_diffract.h"
#include <string.h>
#define MAGIC 0x44494646u
#define VISITED 0x8000u
static const int16_t rays[6][16][2]={
#include "fx_diffract_rays.inc"
};
static const int16_t ring[128][2]={
#include "fx_diffract_ring.inc"
};
size_t fx_diffract_size(unsigned width,unsigned height)
{
    if(width<4||width>720||(width&3)||height<4||height>480||(height&3))return 0;
    size_t count=(size_t)(width/4)*(height/4);
    /* Cells (8 bytes) and BFS queue (2) are dead before the RGB Q8 light
     * accumulator (12) is built, so these transient phases share storage. */
    return sizeof(fx_diffract_work)+count*12;
}
int fx_diffract_validate(const fx_params*p)
{
    return p&&p->value[0]>=3&&p->value[0]<=8&&p->value[1]>=8&&p->value[1]<=160&&!(p->value[1]&3)&&
        p->value[2]<=100&&p->value[3]<=255&&p->value[4]<=100&&p->value[5]<=100;
}
int fx_diffract_ready(const void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch)
{
    size_t size=fx_diffract_size(width,height);
    if(!w||((uintptr_t)w&3)||!size||n<size||!fx_diffract_validate(p)||pitch<width*2||pitch>4096)return 0;
    const fx_diffract_work*a=w;
    return a->magic==MAGIC&&a->width==width&&a->height==height&&a->pitch==pitch&&
        a->tap_count<=FX_DIFFRACT_TAPS&&!memcmp(p,&a->params,sizeof(*p));
}
static int round_div(int value,int divisor)
{return value>=0?(value+divisor/2)/divisor:-((-value+divisor/2)/divisor);}
static void tap(fx_diffract_work*w,int x,int y,unsigned weight,unsigned channel)
{
    fx_diffract_tap*t=&w->taps[w->tap_count++];t->x=(int16_t)x;t->y=(int16_t)y;
    t->weight=(uint16_t)weight;t->channel=(uint8_t)channel;t->pad=0;
}
int fx_diffract_prepare(void*workspace,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch,volatile int*stop)
{
    size_t size=fx_diffract_size(width,height);
    if(!workspace||((uintptr_t)workspace&3)||!size||n<size||!fx_diffract_validate(p)||pitch<width*2||pitch>4096)return FX_INVALID;
    fx_diffract_work*w=workspace;w->magic=0;w->tap_count=0;if(stop&&*stop)return FX_CANCEL;
    unsigned radius=p->value[1]/4,spread=p->value[2];
    for(unsigned direction=0;direction<p->value[0]*2;direction++){
        if(stop&&*stop)return FX_CANCEL;
        for(unsigned j=1;j<=radius;j++)for(unsigned channel=0;channel<3;channel++){
            int scale=100+(1-(int)channel)*(int)spread/3;
            int distance=(int)(j*256)*scale/100;
            tap(w,round_div(rays[p->value[0]-3][direction][0]*distance,16384),
                round_div(rays[p->value[0]-3][direction][1]*distance,16384),
                (radius+1-j)*64*256/(radius+1),channel);
        }
    }
    if(p->value[5])for(unsigned angle=0;angle<128;angle++){
        if(stop&&*stop)return FX_CANCEL;
        for(unsigned channel=0;channel<3;channel++){
            int scale=100+(1-(int)channel)*(int)spread/3;
            int distance=(int)(radius*3*256/5)*scale/100;
            unsigned weight=24*p->value[5]*(radius*3*256/5)*6/(100*128);
            tap(w,round_div(ring[angle][0]*distance,16384),round_div(ring[angle][1]*distance,16384),weight,channel);
        }
    }
    for(unsigned channel=0;channel<3;channel++)tap(w,0,0,32*256,channel);
    w->params=*p;w->width=width;w->height=height;w->pitch=pitch;w->magic=MAGIC;return FX_OK;
}
static int overlaps(const void*a,size_t an,const void*b,size_t bn)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x<=y?y-x<an:x-y<bn;}
static void enqueue(fx_diffract_cell*c,uint16_t*queue,unsigned*tail,unsigned index)
{
    if(c[index].weight&&!(c[index].weight&VISITED)){c[index].weight|=VISITED;queue[(*tail)++]=(uint16_t)index;}
}
static unsigned regions(fx_diffract_work*w,fx_diffract_cell*c,uint16_t*queue,unsigned lw,unsigned lh,uint32_t*total)
{
    unsigned retained=0;*total=0;
    for(unsigned index=0;index<lw*lh;index++)if(c[index].weight&&!(c[index].weight&VISITED)){
        unsigned head=0,tail=0,weight=0,maximum=0,pixels=0;
        uint64_t cx=0,cy=0;enqueue(c,queue,&tail,index);
        while(head<tail){
            unsigned i=queue[head++],x=i%lw,y=i/lw,v=c[i].weight&~VISITED;
            weight+=v;cx+=(uint64_t)(x*4)*v+c[i].x;cy+=(uint64_t)(y*4)*v+c[i].y;
            if(c[i].peak>maximum)maximum=c[i].peak;
            pixels+=c[i].count;
            if(x)enqueue(c,queue,&tail,i-1);
            if(x+1<lw)enqueue(c,queue,&tail,i+1);
            if(y)enqueue(c,queue,&tail,i-lw);
            if(y+1<lh)enqueue(c,queue,&tail,i+lw);
        }
        fx_diffract_peak p={(int32_t)((cx*64+weight/2)/weight)-96,(int32_t)((cy*64+weight/2)/weight)-96,
            maximum*255/(255-w->params.value[3]),pixels,tail};
        (*total)++;
        if(retained<FX_DIFFRACT_SOURCES)w->peaks[retained++]=p;
        else{
            unsigned weakest=0;for(unsigned j=1;j<retained;j++)if(w->peaks[j].strength<w->peaks[weakest].strength)weakest=j;
            if(p.strength>w->peaks[weakest].strength)w->peaks[weakest]=p;
        }
    }
    return retained;
}
static int floor256(int value){return value>=0?value/256:-((-value+255)/256);}
static void splat(uint32_t*light,unsigned lw,unsigned lh,int x,int y,unsigned channel,unsigned energy)
{
    int ix=floor256(x),iy=floor256(y);unsigned fx=(unsigned)(x-ix*256),fy=(unsigned)(y-iy*256);
    for(unsigned dy=0;dy<2;dy++)for(unsigned dx=0;dx<2;dx++){
        int xx=ix+(int)dx,yy=iy+(int)dy;
        if(xx>=0&&yy>=0&&(unsigned)xx<lw&&(unsigned)yy<lh){
            unsigned wx=dx?fx:256-fx,wy=dy?fy:256-fy;
            light[((size_t)yy*lw+(unsigned)xx)*3+channel]+=(energy*wx*wy+32768)>>16;
        }
    }
}
static unsigned read_light(const uint32_t*l,unsigned lw,unsigned lh,int x,int y,unsigned channel)
{return x>=0&&y>=0&&(unsigned)x<lw&&(unsigned)y<lh?l[((size_t)y*lw+(unsigned)x)*3+channel]:0;}
static void light_row(fx_diffract_work*w,const uint32_t*l,unsigned lw,unsigned lh,unsigned y)
{
    int yy=(int)y*64-96,iy=floor256(yy);unsigned fy=(unsigned)(yy-iy*256);
    memset(w->row[0],0,sizeof(w->row[0]));memset(w->row[lw+1],0,sizeof(w->row[0]));
    for(unsigned x=0;x<lw;x++)for(unsigned channel=0;channel<3;channel++)
        w->row[x+1][channel]=(uint16_t)(read_light(l,lw,lh,(int)x,iy,channel)*(256-fy)+
            read_light(l,lw,lh,(int)x,iy+1,channel)*fy);
}
static unsigned interpolate(const fx_diffract_work*w,unsigned x,unsigned channel)
{
    int xx=(int)x*64-96,ix=floor256(xx);unsigned fx=(unsigned)(xx-ix*256);
    return (w->row[ix+1][channel]*(256-fx)+w->row[ix+2][channel]*fx+32768)>>16;
}
static int clamp(int v,int low,int high){return v<low?low:v>high?high:v;}
static void rgb(unsigned y,int u,int v,int out[3])
{
    out[0]=clamp((int)y+1613*v/1024,0,255);out[1]=clamp((int)y-(192*u+479*v)/1024,0,255);
    out[2]=clamp((int)y+1900*u/1024,0,255);
}
int fx_diffract_render(const void*source,void*destination,size_t capacity,void*workspace,size_t work_size,
    const fx_params*p,unsigned width,unsigned height,unsigned pitch,uint32_t stats[7])
{
    if(!source||!destination||!stats||!fx_diffract_ready(workspace,work_size,p,width,height,pitch)||
        (uint64_t)pitch*height>capacity)return FX_INVALID;
    size_t bytes=(size_t)pitch*height,needed=fx_diffract_size(width,height);
    const void*ptr[]={source,destination,workspace,p,stats};const size_t len[]={bytes,bytes,needed,sizeof(*p),28};
    for(unsigned a=0;a<5;a++)for(unsigned b=a+1;b<5;b++)if(overlaps(ptr[a],len[a],ptr[b],len[b]))return FX_INVALID;
    fx_diffract_work*w=workspace;unsigned lw=width/4,lh=height/4,count=lw*lh,bright=0;
    fx_diffract_cell*c=(void*)w->data;uint16_t*queue=(void*)(w->data+count*8);
    uint32_t*light=(void*)w->data;const unsigned char*src=source;unsigned char*dst=destination;
    memset(c,0,count*sizeof(*c));
    for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++){
        unsigned Y=src[(size_t)y*pitch+x*2+1];if(Y<=p->value[3])continue;
        unsigned v=Y-p->value[3];fx_diffract_cell*a=&c[(y/4)*lw+x/4];
        a->weight+=(uint16_t)v;a->x+=(uint16_t)((x&3)*v);a->y+=(uint16_t)((y&3)*v);
        if(v>a->peak)a->peak=(uint8_t)v;
        a->count++;bright++;
    }
    uint32_t total=0;unsigned retained=regions(w,c,queue,lw,lh,&total);
    stats[0]=bright;stats[1]=total;stats[2]=retained;stats[3]=w->tap_count;
    stats[4]=total-retained;stats[5]=lw;stats[6]=lh;
    if(!retained||!p->value[4]){
        for(unsigned y=0;y<height;y++)memcpy(dst+(size_t)y*pitch,src+(size_t)y*pitch,width*2);
        return FX_OK;
    }
    memset(light,0,count*12);
    for(unsigned i=0;i<retained;i++)for(unsigned j=0;j<w->tap_count;j++){
        const fx_diffract_tap*t=&w->taps[j];const fx_diffract_peak*a=&w->peaks[i];
        splat(light,lw,lh,a->x+t->x,a->y+t->y,t->channel,(a->strength*t->weight+127)/255);
    }
    for(unsigned i=0;i<count*3;i++){unsigned v=(light[i]+128)>>8;light[i]=v>255?255:v;}
    for(unsigned y=0;y<height;y++){
      light_row(w,light,lw,lh,y);
      for(unsigned x=0;x<width;x+=2){
        const unsigned char*s=src+(size_t)y*pitch+x*2;unsigned char*d=dst+(size_t)y*pitch+x*2;
        unsigned glow[2][3],active=0;
        for(unsigned k=0;k<2;k++)for(unsigned channel=0;channel<3;channel++){
            glow[k][channel]=interpolate(w,x+k,channel)*p->value[4]/100;active|=glow[k][channel];
        }
        if(!active){memcpy(d,s,4);continue;}
        int u=s[0]<128?s[0]:(int)s[0]-256,v=s[2]<128?s[2]:(int)s[2]-256,us=0,vs=0;
        for(unsigned k=0;k<2;k++){
            int color[3];rgb(s[1+k*2],u,v,color);
            for(unsigned channel=0;channel<3;channel++)color[channel]+=(255-color[channel])*(int)glow[k][channel]/255;
            int Y=(218*color[0]+732*color[1]+74*color[2]+512)/1024;
            d[1+k*2]=(unsigned char)Y;us+=clamp((color[2]-Y)*1024/1900,-128,127);vs+=clamp((color[0]-Y)*1024/1613,-128,127);
        }
        d[0]=(unsigned char)(us/2);d[2]=(unsigned char)(vs/2);
    }
      }
    return FX_OK;
}
