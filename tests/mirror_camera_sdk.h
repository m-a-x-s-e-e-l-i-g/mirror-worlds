#ifndef MIRROR_CAMERA_SDK_H
#define MIRROR_CAMERA_SDK_H
#include <stdint.h>
int is_camera(const char *model,const char *firmware);
uint32_t shamem_read(uint32_t address);
#endif
