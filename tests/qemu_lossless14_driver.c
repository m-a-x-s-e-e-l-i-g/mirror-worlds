#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
int mirror_lj14_encode(const uint16_t*,uint32_t,uint32_t,uint8_t**,size_t*);
int main(int argc,char **argv)
{
    if (argc!=5) return 2;
    unsigned w=strtoul(argv[3],NULL,10),h=strtoul(argv[4],NULL,10);
    if (!w||w%2||!h||(size_t)w*h>24000000) return 2;
    size_t n=(size_t)w*h;
    uint16_t *p=malloc(n*2);uint8_t *out=NULL;size_t size=0;
    FILE *f=fopen(argv[1],"rb");if(!f||!p)return 3;
    if(fread(p,2,n,f)!=n)return 3;fclose(f);
    if(mirror_lj14_encode(p,w,h,&out,&size)) { free(p);return 4; }
    f=fopen(argv[2],"wb");if(!f)return 3;
    if(fwrite(out,1,size,f)!=size)return 3;fclose(f);free(out);free(p);
    return 0;
}
