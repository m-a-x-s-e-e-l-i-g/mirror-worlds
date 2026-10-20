/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade).
 * Native UYVY geometry. Mapping uses fixed-point isometries in physical pixel
 * coordinates. Each Y is sampled independently; U/V are shared/averaged for
 * the output pair. No per-frame trigonometry or modification of Canon input. */
#include "fx_mirror.h"
#include "fx_mirror_edges.h"
#include <string.h>
#include "fx_copy.h"
#define MAGIC 0x4d495252u
static const int16_t sine[91]={
#include "fx_sine.inc"
};
static int sin_deg(int angle)
{
    angle%=360;if(angle<0)angle+=360;
    int sign=angle>=180?-1:1;if(angle>=180)angle-=180;if(angle>90)angle=180-angle;
    return sign*sine[angle];
}
static int cos_deg(int angle){return sin_deg(angle+90);}
static int rounded(int n){return n>=0?(n+16384)/32768:-((-n+16384)/32768);}
static unsigned edge(int v,unsigned extent)
{
    if(extent<=1)return 0;
    int period=(int)(2*(extent-1));v%=period;if(v<0)v+=period;
    return (unsigned)v<extent?(unsigned)v:(unsigned)(period-v);
}
size_t fx_mirror_size(unsigned width,unsigned height)
{
    if(width<4||width>720||(width&1)||!height||height>480)return 0;
    return sizeof(fx_mirror_map)+(size_t)height*16*sizeof(fx_mirror_run);
}
int fx_mirror_validate(const fx_params*p)
{
    if(p&&p->value[0]==FX_MIRROR_EDGES)return fx_edges_valid(p);
    return p&&p->value[0]<180&&p->value[1]>=2&&p->value[1]<=12&&!(p->value[1]&1)&&p->value[2]<=1000&&p->value[3]<=1000;
}
int fx_mirror_ready(const void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch)
{
    if(!w||((uintptr_t)w&3)||!fx_mirror_validate(p)||!fx_mirror_size(width,height)||n<fx_mirror_size(width,height))return 0;
    const fx_mirror_map*m=w;
    return m->magic==MAGIC&&m->width==width&&m->height==height&&m->pitch==pitch&&!memcmp(&m->params,p,sizeof(*p));
}
typedef struct {int x,y,a,b,c,d;} sector;
static unsigned choose(int dx,int dy,unsigned count,const sector*s)
{
    if(count==2)return s[0].x*dy-s[0].y*dx<0?1:0;
    for(unsigned i=0;i<count;i++){
        unsigned next=i+1==count?0:i+1;
        if(s[i].x*dy-s[i].y*dx>=0&&s[next].x*dy-s[next].y*dx<0)return i;
    }
    return 0;
}
static uint32_t mapped(unsigned x,unsigned y,unsigned width,unsigned height,unsigned pitch,
    int cx,int cy,unsigned count,const sector*s)
{
    int dx=(int)(x*2)-cx,dy=(int)(y*2)-cy;unsigned k=choose(dx,dy,count,s);
    int mx=rounded(cx*16384+s[k].a*dx+s[k].b*dy);
    int my=rounded(cy*16384+s[k].c*dx+s[k].d*dy);
    unsigned sx=edge(mx,width),sy=edge(my,height);
    return (sy*pitch+sx*2+1)|((sx&1)?FX_MIRROR_ODD:0);
}
static void fast_columns(fx_mirror_map*m,unsigned width)
{
    uint32_t offsets[360];unsigned pairs=width/2;m->fast_count=0;
    for(unsigned i=0;i<pairs;i++){
        uint32_t a=m->x[i*2],b=m->x[i*2+1];
        unsigned da=(a&FX_MIRROR_ODD)?3:1,db=(b&FX_MIRROR_ODD)?3:1;
        unsigned ua=(a&FX_MIRROR_OFFSET)-da,ub=(b&FX_MIRROR_OFFSET)-db;
        if(ua!=ub||(a&FX_MIRROR_OFFSET)==(b&FX_MIRROR_OFFSET))return;
        offsets[i]=ua|(da==3?FX_MIRROR_ODD:0);
    }
    for(unsigned x=0;x<pairs;){
        unsigned start=x++,swap=offsets[start]&FX_MIRROR_ODD;
        int first=(int)(offsets[start]&FX_MIRROR_OFFSET),step=0;
        if(x<pairs&&(offsets[x]&FX_MIRROR_ODD)==swap)step=(int)(offsets[x]&FX_MIRROR_OFFSET)-first;
        while(x<pairs&&(offsets[x]&FX_MIRROR_ODD)==swap&&
            (int)(offsets[x]&FX_MIRROR_OFFSET)==first+step*(int)(x-start))x++;
        if(m->fast_count==16){m->fast_count=0;return;}
        m->fast[m->fast_count++]=(fx_mirror_xrun){(uint16_t)x,(uint16_t)(swap!=0),(uint32_t)first,step};
    }
}
int fx_mirror_prepare(void*w,size_t n,const fx_params*p,unsigned width,unsigned height,unsigned pitch,volatile int*stop)
{
    if(!w||((uintptr_t)w&3)||!fx_mirror_validate(p)||!fx_mirror_size(width,height)||
        n<fx_mirror_size(width,height)||pitch<width*2||pitch>4096)return FX_INVALID;
    fx_mirror_map*m=w;m->magic=0;if(stop&&*stop)return FX_CANCEL;
    if(p->value[0]==FX_MIRROR_EDGES){
        unsigned mask=p->value[1];
        for(unsigned x=0;x<width;x++){
            unsigned pair=x/2,mapped_pair=fx_edge_coordinate(pair,width/2,p->value[2],mask&1,mask&2);
            unsigned sx=mapped_pair*2+((x&1)^(mapped_pair!=pair));
            m->x[x]=(sx*2+1)|((sx&1)?FX_MIRROR_ODD:0);
        }
        for(unsigned y=0;y<height;y++){
            if(stop&&*stop)return FX_CANCEL;
            m->y[y]=fx_edge_coordinate(y,height,p->value[3],mask&4,mask&8)*pitch;
        }
        fast_columns(m,width);m->params=*p;m->width=width;m->height=height;m->pitch=pitch;m->mode=1;m->magic=MAGIC;
        return FX_OK;
    }
    int cx=(int)(((width-1)*p->value[2]*2+500)/1000);
    int cy=(int)(((height-1)*p->value[3]*2+500)/1000);
    unsigned count=p->value[1],angle=p->value[0],step=360/count;
    sector sectors[12];
    m->center_x=cx;m->center_y=cy;
    for(unsigned k=0;k<count;k++){
        int a=(int)(angle+k*step);sectors[k].x=cos_deg(a);sectors[k].y=sin_deg(a);
        if(!(k&1)){
            int rotation=-(int)(k*step),c=cos_deg(rotation),s=sin_deg(rotation);
            sectors[k].a=c;sectors[k].b=-s;sectors[k].c=s;sectors[k].d=c;
        }else{
            int twice=(int)(2*angle+(k+1)*step),c=cos_deg(twice),s=sin_deg(twice);
            sectors[k].a=c;sectors[k].b=s;sectors[k].c=s;sectors[k].d=-c;
        }
        m->matrix[k]=(fx_mirror_matrix){sectors[k].a,sectors[k].b,sectors[k].c,sectors[k].d};
    }
    for(int i=0;i<3072;i++){m->fold_x[i]=(uint16_t)edge(i-1024,width);m->fold_y[i]=(uint16_t)edge(i-1024,height);}
    /* Axis-aligned 2/4-way maps are separable and fit in a few cache lines per
     * row. Other counts/angles use compact sector runs and fixed-point stepping. */
    int simple=(count==2||count==4)&&(angle==0||angle==90);
    m->fast_count=0;
    if(simple){
        for(unsigned x=0;x<width;x++){
            uint32_t v=mapped(x,0,width,height,pitch,cx,cy,count,sectors);
            m->x[x]=((v&FX_MIRROR_OFFSET)%pitch)|(v&FX_MIRROR_ODD);
        }
        for(unsigned y=0;y<height;y++){
            if(stop&&*stop)return FX_CANCEL;
            m->y[y]=((mapped(0,y,width,height,pitch,cx,cy,count,sectors)&FX_MIRROR_OFFSET)/pitch)*pitch;
        }
        fast_columns(m,width);
    }else for(unsigned y=0;y<height;y++){
        if(stop&&*stop)return FX_CANCEL;
        unsigned nr=0,last=choose(-cx,(int)y*2-cy,count,sectors);
        for(unsigned x=1;x<=width;x++){
            unsigned current=x<width?choose((int)x*2-cx,(int)y*2-cy,count,sectors):count;
            if(current!=last){
                if(nr>=16)return FX_INVALID;
                m->runs[y][nr++]=(fx_mirror_run){(uint16_t)x,(uint16_t)last};last=current;
            }
        }
        m->run_count[y]=(uint16_t)nr;
    }
    m->params=*p;m->width=width;m->height=height;m->pitch=pitch;m->mode=simple?1:2;
    m->magic=MAGIC;return FX_OK;
}
static int overlaps(const void*a,size_t an,const void*b,size_t bn)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x<=y?y-x<an:x-y<bn;}
static unsigned average(unsigned a,unsigned b)
{
    a^=128;b^=128;return (((a+b)/2)^128)&255;
}
typedef uint32_t pixel32 __attribute__((__may_alias__));
typedef struct {unsigned run,x,end;int px,py,dx,dy;} cursor;
static int coordinate(const fx_mirror_map*m,unsigned y,cursor*c,uint32_t*out)
{
    if(c->x==c->end){
        if(c->run>=m->run_count[y])return 0;
        fx_mirror_run r=m->runs[y][c->run++];if(r.sector>=12||r.end<=c->x||r.end>m->width)return 0;
        const fx_mirror_matrix*a=&m->matrix[r.sector];int dx=(int)c->x*2-m->center_x,dy=(int)y*2-m->center_y;
        c->px=m->center_x*16384+a->a*dx+a->b*dy;c->py=m->center_y*16384+a->c*dx+a->d*dy;
        c->dx=a->a*2;c->dy=a->c*2;c->end=r.end;
    }
    int ix=rounded(c->px)+1024,iy=rounded(c->py)+1024;
    if(ix<0||ix>=3072||iy<0||iy>=3072)return 0;
    unsigned x=m->fold_x[ix],sy=m->fold_y[iy];
    *out=(sy*m->pitch+x*2+1)|((x&1)?FX_MIRROR_ODD:0);
    c->x++;c->px+=c->dx;c->py+=c->dy;return 1;
}
int fx_mirror_render(const void*source,void*destination,size_t capacity,const void*w,size_t n,
    const fx_params*p,unsigned width,unsigned height,unsigned pitch)
{
    if(!fx_mirror_ready(w,n,p,width,height,pitch)||!source||!destination||pitch<width*2||pitch>4096||
        (uint64_t)pitch*height>capacity)return FX_INVALID;
    size_t bytes=(size_t)pitch*height;
    if(overlaps(source,bytes,destination,bytes)||overlaps(w,fx_mirror_size(width,height),source,bytes)||
        overlaps(w,fx_mirror_size(width,height),destination,bytes))return FX_INVALID;
    const fx_mirror_map*m=w;const unsigned char*src=source;unsigned char*dst=destination;
    int aligned=!(((uintptr_t)source|(uintptr_t)destination|pitch)&3);
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
    aligned=0;
#endif
    for(unsigned y=0;y<height;y++){
      if(aligned&&m->mode==1&&m->fast_count){
        unsigned x=0;const unsigned char*row=src+m->y[y];pixel32*out=(pixel32*)(dst+(size_t)y*pitch);
        for(unsigned i=0;i<m->fast_count;i++){
            const fx_mirror_xrun*r=&m->fast[i];unsigned length=r->end-x;
            if(r->step==4&&!r->swap){
                fx_copy_cpu(out+x,row+r->start,length*4);
            }
            else for(unsigned j=0;j<length;j++){
                int offset=(int)r->start+r->step*(int)j;uint32_t v=*(const pixel32*)(row+offset);
                if(r->swap)v=(v&0x00ff00ffu)|((v&0xff000000u)>>16)|((v&0x0000ff00u)<<16);
                out[x+j]=v;
            }
            x=r->end;
        }
        continue;
      }
      cursor current={0};
      for(unsigned x=0;x<width/2;x++){
        uint32_t ea,eb;
        if(m->mode==1){ea=((m->x[x*2]&FX_MIRROR_OFFSET)+m->y[y])|(m->x[x*2]&FX_MIRROR_ODD);
            eb=((m->x[x*2+1]&FX_MIRROR_OFFSET)+m->y[y])|(m->x[x*2+1]&FX_MIRROR_ODD);}
        else if(!coordinate(m,y,&current,&ea)||!coordinate(m,y,&current,&eb))return FX_INVALID;
        unsigned a=ea&FX_MIRROR_OFFSET,b=eb&FX_MIRROR_OFFSET;
        unsigned da=(ea&FX_MIRROR_ODD)?3:1,db=(eb&FX_MIRROR_ODD)?3:1;
        if(a>=bytes||b>=bytes||a<da||b<db||a-da+2>=bytes||b-db+2>=bytes)return FX_INVALID;
        unsigned ua=a-da,ub=b-db;unsigned char*out=dst+(size_t)y*pitch+x*4;
        if(aligned&&ua==ub&&a!=b){
            uint32_t v=*(const pixel32*)(src+ua);
            if(da==3)v=(v&0x00ff00ffu)|((v&0xff000000u)>>16)|((v&0x0000ff00u)<<16);
            *(pixel32*)out=v;
        }else{
            out[0]=(unsigned char)average(src[ua],src[ub]);out[2]=(unsigned char)average(src[ua+2],src[ub+2]);
            out[1]=src[a];out[3]=src[b];
        }
      }
    }
    return FX_OK;
}
