/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade).
 * Full sensor CFA mapping with the preview's fixed-point sector convention.
 * Reads packed Canon14 or U16 without modifying source or optical black. */
#include "fx_mirror_raw.h"
#include "fx_mirror_edges.h"
#include <string.h>
#define MAGIC 0x524d4952u
static const int16_t sine[91]={
#include "fx_sine.inc"
};
static int overlaps(const void*a,size_t an,const void*b,size_t bn)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x<=y?y-x<an:x-y<bn;}
static int sin_deg(int n)
{n%=360;if(n<0)n+=360;int sign=n>=180?-1:1;if(n>=180)n-=180;if(n>90)n=180-n;return sign*sine[n];}
static int cos_deg(int n){return sin_deg(n+90);}
static int rounded(int n){return n>=0?(n+16384)/32768:-((-n+16384)/32768);}
static unsigned edge(int v,unsigned extent)
{if(extent<=1)return 0;int period=(int)(extent-1)*2;v%=period;if(v<0)v+=period;return (unsigned)v<extent?(unsigned)v:(unsigned)(period-v);}
static int valid_frame(const gl_frame*f)
{
    if(!f||!f->data||f->width<2||f->width>8192||f->height<2||f->height>8192||
        (f->width&1)||(uint64_t)f->width*f->height>30000000||f->format>GL_CANON14||
        f->black>=f->white||f->white>16383||(f->format==GL_CANON14&&(f->width&7)))return 0;
    uint64_t row=f->format==GL_U16?(uint64_t)f->width*2:(uint64_t)f->width*14/8;
    return f->pitch>=row&&(uint64_t)f->pitch*f->height<=f->size&&
        (uintptr_t)f->data<=UINTPTR_MAX-f->size;
}
int fx_mirror_raw_prepare(fx_mirror_raw*m,const gl_frame*f,const uint32_t r[4],const fx_params*p,volatile int*stop)
{
    if(!m||((uintptr_t)m&3)||!valid_frame(f)||!r||!p||
        (p->value[0]==FX_MIRROR_EDGES?!fx_edges_valid(p):(p->value[0]>=180||p->value[1]<2||p->value[1]>12||
        (p->value[1]&1)||p->value[2]>1000||p->value[3]>1000))||r[0]>=r[2]||r[1]>=r[3]||r[2]>f->height||r[3]>f->width||
        overlaps(m,sizeof(*m),f->data,f->size)||overlaps(m,sizeof(*m),f,sizeof(*f))||
        overlaps(m,sizeof(*m),r,16)||overlaps(m,sizeof(*m),p,sizeof(*p)))return FX_INVALID;
    m->magic=0;if(stop&&*stop)return FX_CANCEL;
    unsigned left=(r[1]+1)&~1u,top=(r[0]+1)&~1u,right=r[3]&~1u,bottom=r[2]&~1u;
    if(right<=left||bottom<=top)return FX_INVALID;
    m->source=*f;m->params=*p;m->left=left;m->top=top;m->right=right;m->bottom=bottom;
    m->cells_w=(right-left)/2;m->cells_h=(bottom-top)/2;m->stop=stop;
    if(p->value[0]==FX_MIRROR_EDGES){m->magic=MAGIC;return FX_OK;}
    m->center_x=(int)(((m->cells_w-1)*p->value[2]*2+500)/1000);
    m->center_y=(int)(((m->cells_h-1)*p->value[3]*2+500)/1000);
    unsigned step=360/p->value[1];
    for(unsigned k=0;k<p->value[1];k++){
        int angle=(int)(p->value[0]+k*step);fx_mirror_raw_sector*s=&m->sector[k];
        s->x=cos_deg(angle);s->y=sin_deg(angle);
        if(!(k&1)){int a=-(int)(k*step);s->a=cos_deg(a);s->b=-sin_deg(a);s->c=sin_deg(a);s->d=cos_deg(a);}
        else{int a=(int)(2*p->value[0]+(k+1)*step);s->a=cos_deg(a);s->b=sin_deg(a);s->c=sin_deg(a);s->d=-cos_deg(a);}
    }
    m->magic=MAGIC;return FX_OK;
}
static void point(const fx_mirror_raw*m,unsigned x,unsigned y,unsigned out[2])
{
    if(x<m->left||x>=m->right||y<m->top||y>=m->bottom){out[0]=x;out[1]=y;return;}
    if(m->params.value[0]==FX_MIRROR_EDGES){
        unsigned mask=m->params.value[1];
        out[0]=m->left+fx_edge_coordinate((x-m->left)/2,m->cells_w,m->params.value[2],mask&1,mask&2)*2+(x&1);
        out[1]=m->top+fx_edge_coordinate((y-m->top)/2,m->cells_h,m->params.value[3],mask&4,mask&8)*2+(y&1);
        return;
    }
    int dx=(int)((x-m->left)/2)*2-m->center_x,dy=(int)((y-m->top)/2)*2-m->center_y;
    unsigned k=0,count=m->params.value[1];
    if(count==2)k=m->sector[0].x*dy-m->sector[0].y*dx<0?1:0;
    else for(unsigned i=0;i<count;i++){
        unsigned n=i+1==count?0:i+1;
        if(m->sector[i].x*dy-m->sector[i].y*dx>=0&&m->sector[n].x*dy-m->sector[n].y*dx<0){k=i;break;}
    }
    const fx_mirror_raw_sector*s=&m->sector[k];
    int xx=rounded(m->center_x*16384+s->a*dx+s->b*dy),yy=rounded(m->center_y*16384+s->c*dx+s->d*dy);
    out[0]=m->left+edge(xx,m->cells_w)*2+(x&1);out[1]=m->top+edge(yy,m->cells_h)*2+(y&1);
}
int fx_mirror_raw_point(const fx_mirror_raw*m,unsigned x,unsigned y,unsigned out[2])
{
    if(!m||m->magic!=MAGIC||!out||x>=m->source.width||y>=m->source.height||
        overlaps(out,8,m,sizeof(*m))||overlaps(out,8,m->source.data,m->source.size))return FX_INVALID;
    if(m->stop&&*m->stop)return FX_CANCEL;
    point(m,x,y,out);return FX_OK;
}
static unsigned word(const unsigned char*p){return p[0]|((unsigned)p[1]<<8);}
static uint16_t sample(const gl_frame*f,unsigned x,unsigned y)
{
    const unsigned char*row=(const unsigned char*)f->data+(size_t)y*f->pitch;
    if(f->format==GL_U16)return (uint16_t)word(row+x*2);
    unsigned bit=x*14,shift=bit&15;row+=(bit/16)*2;unsigned a=word(row);
    if(shift<=2)return (uint16_t)((a>>(2-shift))&16383);
    return (uint16_t)(((a<<(shift-2))|(word(row+2)>>(18-shift)))&16383);
}
int fx_mirror_raw_sample(const fx_mirror_raw*m,unsigned x,unsigned y,uint16_t*out)
{
    if(!m||m->magic!=MAGIC||!out||((uintptr_t)out&1)||x>=m->source.width||y>=m->source.height||
        overlaps(out,2,m,sizeof(*m))||overlaps(out,2,m->source.data,m->source.size))return FX_INVALID;
    if(m->stop&&*m->stop)return FX_CANCEL;
    unsigned xy[2];point(m,x,y,xy);*out=sample(&m->source,xy[0],xy[1]);return FX_OK;
}
int fx_mirror_raw_row(const fx_mirror_raw*m,unsigned y,uint16_t*out,size_t samples)
{
    if(!m||m->magic!=MAGIC||!out||((uintptr_t)out&1)||y>=m->source.height||samples<m->source.width||samples>SIZE_MAX/2||
        overlaps(out,samples*2,m,sizeof(*m))||overlaps(out,samples*2,m->source.data,m->source.size))return FX_INVALID;
    if(m->stop&&*m->stop)return FX_CANCEL;
    for(unsigned x=0;x<m->source.width;x++){
        if(!(x&255)&&m->stop&&*m->stop)return FX_CANCEL;
        unsigned xy[2];point(m,x,y,xy);out[x]=sample(&m->source,xy[0],xy[1]);
    }
    return FX_OK;
}
